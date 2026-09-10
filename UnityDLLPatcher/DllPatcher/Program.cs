using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Mono.Cecil;
using Mono.Cecil.Cil;

internal static class Program
{
    private const string GameManagedDirectory =
        @"F:\SteamLibrary\steamapps\common\東京サイコデミック\TOKYO_PSYCHODEMIC_Data\Managed";

    private const string OriginalDll =
        GameManagedDirectory + @"\Assembly-CSharp.dll";

    private const string BackupDll =
        GameManagedDirectory + @"\Assembly-CSharp.dll.ORIGINAL";

    private const string PatchedDll =
        GameManagedDirectory + @"\Assembly-CSharp.ENGLISHONLY.dll";

    private static int _languageWritesPatched;
    private static int _getterPatched;

    private static void Main()
    {
        Console.WriteLine();
        Console.WriteLine("TOKYO PSYCHODEMIC - ENGLISH ONLY DLL PATCHER");
        Console.WriteLine(new string('=', 70));
        Console.WriteLine();

        Console.WriteLine("Originale:");
        Console.WriteLine(OriginalDll);
        Console.WriteLine();

        if (!Directory.Exists(GameManagedDirectory))
        {
            Fail(
                "Cartella Managed non trovata:\n" +
                GameManagedDirectory
            );
            return;
        }

        if (!File.Exists(OriginalDll))
        {
            Fail(
                "Assembly-CSharp.dll non trovato:\n" +
                OriginalDll
            );
            return;
        }

        // ------------------------------------------------------------
        // BACKUP
        // ------------------------------------------------------------

        EnsureBackup();

        // ------------------------------------------------------------
        // RESOLVER UNITY
        // ------------------------------------------------------------

        var resolver = new DefaultAssemblyResolver();

        resolver.AddSearchDirectory(GameManagedDirectory);

        // Alcune build Unity usano anche Plugin/
        var pluginsDirectory =
            Path.Combine(GameManagedDirectory, "Plugins");

        if (Directory.Exists(pluginsDirectory))
        {
            resolver.AddSearchDirectory(pluginsDirectory);
        }

        // ------------------------------------------------------------
        // READ ASSEMBLY
        // ------------------------------------------------------------

        Console.WriteLine("Caricamento assembly...");

        var readerParameters = new ReaderParameters
        {
            ReadSymbols = false,
            InMemory = false,
            AssemblyResolver = resolver
        };

        AssemblyDefinition? assembly = null;

        try
        {
            assembly = AssemblyDefinition.ReadAssembly(
                OriginalDll,
                readerParameters
            );

            Console.WriteLine(
                $"Assembly: {assembly.Name.Name}"
            );
            Console.WriteLine();

            var module = assembly.MainModule;

            // --------------------------------------------------------
            // SYSTEMDATA
            // --------------------------------------------------------

            var systemDataType =
                FindType(module, "SystemData");

            if (systemDataType == null)
            {
                throw new InvalidOperationException(
                    "Tipo SystemData non trovato."
                );
            }

            Console.WriteLine(
                $"SystemData trovato: {systemDataType.FullName}"
            );

            var languageField =
                systemDataType.Fields.FirstOrDefault(
                    f =>
                        f.Name == "language" &&
                        IsELanguageField(f)
                );

            if (languageField == null)
            {
                throw new InvalidOperationException(
                    "Campo SystemData.language non trovato."
                );
            }

            Console.WriteLine(
                $"Campo lingua trovato: {languageField.FullName}"
            );

            // --------------------------------------------------------
            // eLanguage
            // --------------------------------------------------------

            var eLanguageType =
                languageField.FieldType.Resolve();

            if (eLanguageType == null)
            {
                throw new InvalidOperationException(
                    "Impossibile risolvere eLanguage."
                );
            }

            var englishField =
                eLanguageType.Fields.FirstOrDefault(
                    f => f.Name == "English"
                );

            if (englishField == null)
            {
                throw new InvalidOperationException(
                    "Valore eLanguage.English non trovato."
                );
            }

            Console.WriteLine(
                $"eLanguage.English trovato: {englishField.FullName}"
            );

            Console.WriteLine();

            // --------------------------------------------------------
            // PATCH SCRITTURE
            // --------------------------------------------------------

            Console.WriteLine(
                "Cerco tutte le istruzioni IL che scrivono SystemData.language..."
            );

            foreach (var type in AllTypes(module))
            {
                foreach (var method in type.Methods)
                {
                    if (!method.HasBody)
                        continue;

                    PatchLanguageFieldWrites(
                        method,
                        languageField,
                        englishField
                    );
                }
            }

            // --------------------------------------------------------
            // PATCH GETTER
            // --------------------------------------------------------

            Console.WriteLine(
                "Cerco SystemDataManager.get_systemData..."
            );

            var systemDataManagerType =
                FindType(module, "SystemDataManager");

            if (systemDataManagerType == null)
            {
                throw new InvalidOperationException(
                    "Tipo SystemDataManager non trovato."
                );
            }

            var getter =
                systemDataManagerType.Methods.FirstOrDefault(
                    m =>
                        m.Name == "get_systemData" &&
                        m.IsStatic
                );

            if (getter == null)
            {
                throw new InvalidOperationException(
                    "Getter SystemDataManager.systemData non trovato."
                );
            }

            PatchSystemDataGetter(
                getter,
                languageField,
                englishField
            );

            // --------------------------------------------------------
            // WRITE
            // --------------------------------------------------------

            Console.WriteLine();
            Console.WriteLine("Scrittura DLL patchato...");

            var writerParameters = new WriterParameters
            {
                WriteSymbols = false
            };

            assembly.Write(
                PatchedDll,
                writerParameters
            );

            Console.WriteLine("Scrittura completata.");

            Console.WriteLine();
            Console.WriteLine(new string('=', 70));
            Console.WriteLine("PATCH COMPLETATA");
            Console.WriteLine(new string('=', 70));
            Console.WriteLine();

            Console.WriteLine(
                $"Scritture SystemData.language patchate: {_languageWritesPatched}"
            );

            Console.WriteLine(
                $"Getter systemData patchato: {_getterPatched}"
            );

            Console.WriteLine();
            Console.WriteLine("Backup originale:");
            Console.WriteLine(BackupDll);

            Console.WriteLine();
            Console.WriteLine("DLL patchato:");
            Console.WriteLine(PatchedDll);

            Console.WriteLine();
            Console.WriteLine(
                "NON sostituire ancora Assembly-CSharp.dll."
            );

            Console.WriteLine(
                "Adesso controlliamo che il DLL patchato sia leggibile."
            );
        }
        catch (Exception ex)
        {
            Console.ForegroundColor = ConsoleColor.Red;

            Console.WriteLine();
            Console.WriteLine("ERRORE DURANTE LA PATCH");
            Console.WriteLine(new string('-', 70));
            Console.WriteLine(ex);

            Console.ResetColor();
        }
        finally
        {
            assembly?.Dispose();
        }
    }

    // ============================================================
    // BACKUP
    // ============================================================

    private static void EnsureBackup()
    {
        if (File.Exists(BackupDll))
        {
            Console.WriteLine(
                "Backup già presente; non viene sovrascritto."
            );
            return;
        }

        Console.WriteLine(
            "Creo backup del DLL originale..."
        );

        File.Copy(
            OriginalDll,
            BackupDll,
            overwrite: false
        );

        Console.WriteLine(
            $"Backup creato: {BackupDll}"
        );

        Console.WriteLine();
    }

    // ============================================================
    // FIELD CHECK
    // ============================================================

    private static bool IsELanguageField(
        FieldDefinition field)
    {
        return field.FieldType.FullName == "eLanguage";
    }

    // ============================================================
    // PATCH DIRECT WRITES
    // ============================================================

    private static void PatchLanguageFieldWrites(
        MethodDefinition method,
        FieldDefinition languageField,
        FieldDefinition englishField)
    {
        var il = method.Body.GetILProcessor();

        var instructions =
            method.Body.Instructions.ToList();

        foreach (var instruction in instructions)
        {
            if (instruction.OpCode.Code != Code.Stfld)
                continue;

            if (instruction.Operand is not FieldReference fieldReference)
                continue;

            FieldDefinition? resolvedField = null;

            try
            {
                resolvedField =
                    fieldReference.Resolve();
            }
            catch
            {
                // Se un campo esterno non è risolvibile,
                // semplicemente ignoralo.
                continue;
            }

            if (resolvedField == null)
                continue;

            if (resolvedField.MetadataToken !=
                languageField.MetadataToken)
            {
                continue;
            }

            /*
             * Stack prima di stfld:
             *
             *     object
             *     value
             *
             * Inseriamo:
             *
             *     pop
             *     ldc.i4 2
             *
             * Risultato:
             *
             *     object
             *     English
             */

            il.InsertBefore(
                instruction,
                Instruction.Create(OpCodes.Pop)
            );

            il.InsertBefore(
                instruction,
                Instruction.Create(
                    OpCodes.Ldc_I4,
                    2
                )
            );

            _languageWritesPatched++;

            Console.WriteLine(
                $"  PATCH: {method.DeclaringType.FullName}::{method.Name}"
            );
        }
    }

    // ============================================================
    // PATCH GETTER
    // ============================================================

    private static void PatchSystemDataGetter(
        MethodDefinition getter,
        FieldDefinition languageField,
        FieldDefinition englishField)
    {
        if (!getter.HasBody)
            return;

        var il =
            getter.Body.GetILProcessor();

        var ret =
            getter.Body.Instructions
                .LastOrDefault(
                    i => i.OpCode == OpCodes.Ret
                );

        if (ret == null)
        {
            throw new InvalidOperationException(
                "RET del getter systemData non trovato."
            );
        }

        /*
         * Prima:
         *
         *     ... m_SystemData
         *     ret
         *
         * Dopo:
         *
         *     ... m_SystemData
         *     dup
         *     ldc.i4 2
         *     stfld SystemData.language
         *     ret
         */

        il.InsertBefore(
            ret,
            Instruction.Create(OpCodes.Dup)
        );

        il.InsertBefore(
            ret,
            Instruction.Create(
                OpCodes.Ldc_I4,
                2
            )
        );

        il.InsertBefore(
            ret,
            Instruction.Create(
                OpCodes.Stfld,
                languageField
            )
        );

        _getterPatched++;

        Console.WriteLine(
            "  PATCH: SystemDataManager.get_systemData"
        );
    }

    // ============================================================
    // ALL TYPES
    // ============================================================

    private static IEnumerable<TypeDefinition> AllTypes(
        ModuleDefinition module)
    {
        foreach (var type in module.Types)
        {
            foreach (var result in AllTypesRecursive(type))
            {
                yield return result;
            }
        }
    }

    private static IEnumerable<TypeDefinition> AllTypesRecursive(
        TypeDefinition type)
    {
        yield return type;

        foreach (var nested in type.NestedTypes)
        {
            foreach (var result in AllTypesRecursive(nested))
            {
                yield return result;
            }
        }
    }

    // ============================================================
    // FIND TYPE
    // ============================================================

    private static TypeDefinition? FindType(
        ModuleDefinition module,
        string shortName)
    {
        foreach (var type in AllTypes(module))
        {
            if (type.Name == shortName)
                return type;
        }

        return null;
    }

    // ============================================================
    // FAIL
    // ============================================================

    private static void Fail(string message)
    {
        Console.ForegroundColor =
            ConsoleColor.Red;

        Console.WriteLine();
        Console.WriteLine(message);

        Console.ResetColor();
    }
}
