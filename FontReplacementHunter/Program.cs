using System;
using System.IO;
using System.Threading;
using System.Collections.Generic;
using AssetsTools.NET;
using AssetsTools.NET.Extra;

class Program
{
    static AssetsManager? am;
    static BundleFileInstance? bundleInst;
    static AssetsFileInstance? assetsInst;
    static AssetsFile? assets;

    static void Main(string[] args)
    {
        Console.OutputEncoding = System.Text.Encoding.UTF8;

        int exitCode;

        try
        {
            if (args.Length == 0)
            {
                exitCode = RunVerify();
            }
            else if (args.Length >= 2)
            {
                string bundlePath = args[0];

                if (!File.Exists(bundlePath))
                {
                    Console.WriteLine("ERRORE: bundle non trovato:");
                    Console.WriteLine(bundlePath);
                    exitCode = 1;
                }
                else
                {
                    List<long> targetTMP = new List<long>();
                    bool valid = true;

                    for (int i = 1; i < args.Length; i++)
                    {
                        if (!long.TryParse(args[i], out long tmpPathID))
                        {
                            Console.WriteLine($"ERRORE: TMP PathID non valido: {args[i]}");
                            valid = false;
                            break;
                        }

                        targetTMP.Add(tmpPathID);
                    }

                    if (!valid || targetTMP.Count == 0)
                    {
                        exitCode = 1;
                    }
                    else
                    {
                        exitCode = RunPatch(bundlePath, targetTMP.ToArray());
                    }
                }
            }
            else
            {
                PrintUsage();
                exitCode = 1;
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine();
            Console.WriteLine("ERRORE FATALE:");
            Console.WriteLine(ex);
            exitCode = 1;
        }
        finally
        {
            SafeReleaseAssetsTools();
        }

        Environment.ExitCode = exitCode;
    }


    // ========================================================
    // USAGE
    // ========================================================

    static void PrintUsage()
    {
        Console.WriteLine("USO:");
        Console.WriteLine("  FontReplacementHunter.exe");
        Console.WriteLine();
        Console.WriteLine("  FontReplacementHunter.exe <bundle> <tmp1> [tmp2] [tmp3] ...");
        Console.WriteLine();
        Console.WriteLine("Il primo argomento è il bundle.");
        Console.WriteLine("Tutti gli argomenti successivi sono i PathID dei TMP/lettere da patchare.");
        Console.WriteLine();
        Console.WriteLine("Per ogni TMP il programma trova automaticamente:");
        Console.WriteLine("  TMP -> InteractCharacter -> Image");
        Console.WriteLine("  TMP -> InteractCharacter -> OutlineImage -> Image");
    }


    // ========================================================
    // PATCH MODE
    // ========================================================

    static int RunPatch(string bundlePath, long[] targetTMP)
    {
        Console.WriteLine("============================================================");
        Console.WriteLine("PATCH TARGET IMAGES");
        Console.WriteLine("============================================================");
        Console.WriteLine();

        Console.WriteLine("Bundle:");
        Console.WriteLine(bundlePath);
        Console.WriteLine();

        Console.WriteLine($"Numero TMP target: {targetTMP.Length}");

        for (int i = 0; i < targetTMP.Length; i++)
        {
            Console.WriteLine($"TMP[{i + 1}] = {targetTMP[i]}");
        }

        Console.WriteLine();

        string tempPath = bundlePath + ".tmp";

        try
        {
            if (!File.Exists(bundlePath))
            {
                Console.WriteLine("ERRORE: bundle non trovato.");
                return 1;
            }

            // ------------------------------------------------
            // LOAD
            // ------------------------------------------------

            am = new AssetsManager();

            bundleInst = am.LoadBundleFile(bundlePath, true);

            Console.WriteLine("Bundle loaded.");
            Console.WriteLine();

            int assetsIndex = FindAssetsFileIndex();

            if (assetsIndex < 0)
            {
                Console.WriteLine("ERRORE: AssetsFile non trovato.");
                return 1;
            }

            assetsInst = am.LoadAssetsFileFromBundle(bundleInst, assetsIndex, false);
            assets = assetsInst.file;

            Console.WriteLine($"Unity: {assets.Metadata.UnityVersion}");
            Console.WriteLine();

            bool[] processed = new bool[targetTMP.Length];
            int totalModified = 0;

            // ------------------------------------------------
            // PATCH ALL TMP TARGETS
            // ------------------------------------------------

            for (int i = 0; i < targetTMP.Length; i++)
            {
                long tmpPathID = targetTMP[i];

                Console.WriteLine("============================================================");
                Console.WriteLine($"TMP TARGET [{i + 1}/{targetTMP.Length}]: {tmpPathID}");
                Console.WriteLine("============================================================");

                AssetFileInfo? tmpInfo = FindAsset(tmpPathID);

                if (tmpInfo == null)
                {
                    Console.WriteLine("TMP NON TROVATO.");
                    Console.WriteLine();
                    continue;
                }

                AssetFileInfo? tmpGOInfo = FindOwnerGameObject(tmpPathID);

                if (tmpGOInfo == null)
                {
                    Console.WriteLine("GameObject TMP NON TROVATO.");
                    Console.WriteLine();
                    continue;
                }

                long tmpTransformID = FindTransformPathID(tmpGOInfo);

                if (tmpTransformID == 0)
                {
                    Console.WriteLine("Transform TMP NON TROVATO.");
                    Console.WriteLine();
                    continue;
                }

                AssetFileInfo? tmpTransformInfo = FindAsset(tmpTransformID);

                if (tmpTransformInfo == null)
                {
                    Console.WriteLine("Transform TMP asset non trovato.");
                    Console.WriteLine();
                    continue;
                }

                dynamic tmpTransform = am.GetBaseField(assetsInst, tmpTransformInfo);

                long fatherTransformID = ReadLong(tmpTransform["m_Father"]["m_PathID"]);

                if (fatherTransformID == 0)
                {
                    Console.WriteLine("Parent Transform non trovato.");
                    Console.WriteLine();
                    continue;
                }

                AssetFileInfo? fatherTransformInfo = FindAsset(fatherTransformID);

                if (fatherTransformInfo == null)
                {
                    Console.WriteLine("Parent Transform asset non trovato.");
                    Console.WriteLine();
                    continue;
                }

                dynamic fatherTransform = am.GetBaseField(assetsInst, fatherTransformInfo);

                long fatherGOID = ReadLong(fatherTransform["m_GameObject"]["m_PathID"]);

                if (fatherGOID == 0)
                {
                    Console.WriteLine("Parent GameObject non trovato.");
                    Console.WriteLine();
                    continue;
                }

                AssetFileInfo? fatherGOInfo = FindAsset(fatherGOID);

                if (fatherGOInfo == null)
                {
                    Console.WriteLine("Parent GameObject asset non trovato.");
                    Console.WriteLine();
                    continue;
                }

                dynamic fatherGO = am.GetBaseField(assetsInst, fatherGOInfo);

                Console.WriteLine($"InteractCharacter = {SafeString(fatherGO, "m_Name")}");
                Console.WriteLine();

                bool parentPatched = PatchFirstImage(fatherGO, "PARENT IMAGE");
                bool outlinePatched = PatchOutlineImage(fatherTransform);

                if (parentPatched && outlinePatched)
                {
                    processed[i] = true;
                    totalModified += 2;

                    Console.WriteLine();
                    Console.WriteLine("TARGET PATCHATO: 2/2 IMAGE");
                }
                else if (parentPatched || outlinePatched)
                {
                    Console.WriteLine();
                    Console.WriteLine("ATTENZIONE: target parzialmente patchato.");
                }
                else
                {
                    Console.WriteLine();
                    Console.WriteLine("NESSUN IMAGE PATCHATO.");
                }

                Console.WriteLine();
            }

            // ------------------------------------------------
            // CHECK ALL TARGETS
            // ------------------------------------------------

            bool allTargetsProcessed = true;

            for (int i = 0; i < processed.Length; i++)
            {
                if (!processed[i])
                {
                    allTargetsProcessed = false;

                    Console.WriteLine(
                        $"ATTENZIONE: TMP non completato: {targetTMP[i]}"
                    );
                }
            }

            if (!allTargetsProcessed)
            {
                Console.WriteLine();
                Console.WriteLine("PATCH ABORTITA:");
                Console.WriteLine("non tutti i TMP target sono stati patchati.");
                return 1;
            }

            int expectedImages = targetTMP.Length * 2;

            if (totalModified != expectedImages)
            {
                Console.WriteLine();
                Console.WriteLine("PATCH ABORTITA:");
                Console.WriteLine(
                    $"Image modificati: {totalModified}/{expectedImages}"
                );
                return 1;
            }

            // ------------------------------------------------
            // WRITE ASSETS FILE
            // ------------------------------------------------

            Console.WriteLine("============================================================");
            Console.WriteLine("SCRITTURA BUNDLE");
            Console.WriteLine("============================================================");

            byte[] newAssetsData;

            using (MemoryStream ms = new MemoryStream())
            {
                AssetsFileWriter assetsWriter = new AssetsFileWriter(ms);

                assets.Write(
                    assetsWriter,
                    0
                );

                newAssetsData = ms.ToArray();
            }

            if (newAssetsData.Length == 0)
            {
                Console.WriteLine("ERRORE: AssetsFile riscritto vuoto.");
                return 1;
            }

            if (assetsInst == null || string.IsNullOrEmpty(assetsInst.name))
            {
                Console.WriteLine("ERRORE: nome AssetsFile non disponibile.");
                return 1;
            }

            bool replaced = false;

            foreach (var dirInfo in bundleInst!.file.BlockAndDirInfo.DirectoryInfos)
            {
                if (dirInfo.Name == assetsInst.name)
                {
                    dirInfo.Replacer =
                        new ContentReplacerFromBuffer(newAssetsData);

                    replaced = true;
                    break;
                }
            }

            if (!replaced)
            {
                Console.WriteLine(
                    "ERRORE: DirectoryInfo dell'AssetsFile non trovata."
                );
                return 1;
            }

            // ------------------------------------------------
            // CREATE TEMP BUNDLE
            // ------------------------------------------------

            if (File.Exists(tempPath))
            {
                try
                {
                    File.Delete(tempPath);
                }
                catch (Exception ex)
                {
                    Console.WriteLine("ERRORE eliminando vecchio temp:");
                    Console.WriteLine(ex);
                    return 1;
                }
            }

            using (FileStream fs = new FileStream(
                tempPath,
                FileMode.CreateNew,
                FileAccess.Write,
                FileShare.None))
            {
                AssetsFileWriter bundleWriter =
                    new AssetsFileWriter(fs);

                bundleInst.file.Write(bundleWriter);
            }

            if (!File.Exists(tempPath))
            {
                Console.WriteLine("ERRORE: temp bundle non creato.");
                return 1;
            }

            long tempSize = new FileInfo(tempPath).Length;

            if (tempSize <= 0)
            {
                Console.WriteLine("ERRORE: temp bundle vuoto.");
                return 1;
            }

            Console.WriteLine();
            Console.WriteLine("Temp bundle creato:");
            Console.WriteLine(tempPath);
            Console.WriteLine($"Size: {tempSize:N0} bytes");

            // ------------------------------------------------
            // RELEASE ASSETS TOOLS
            // ------------------------------------------------

            Console.WriteLine();
            Console.WriteLine(
                "Rilascio AssetsTools.NET prima della sostituzione..."
            );

            SafeReleaseAssetsTools();

            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();

            // ------------------------------------------------
            // REPLACE ORIGINAL
            // ------------------------------------------------

            if (!ReplaceBundleWithRetry(tempPath, bundlePath))
            {
                Console.WriteLine();
                Console.WriteLine(
                    "ERRORE: impossibile sostituire il bundle originale."
                );

                Console.WriteLine(
                    "Il file .tmp viene lasciato per non perdere il risultato."
                );

                return 1;
            }

            Console.WriteLine();
            Console.WriteLine("Bundle originale sostituito.");

            // ------------------------------------------------
            // VERIFY WRITTEN BUNDLE
            // ------------------------------------------------

            Console.WriteLine();
            Console.WriteLine("============================================================");
            Console.WriteLine("VERIFICA POST-SCRITTURA");
            Console.WriteLine("============================================================");

            bool verifyOK = VerifyBundle(
                bundlePath,
                targetTMP,
                true
            );

            if (!verifyOK)
            {
                Console.WriteLine();
                Console.WriteLine("PATCH FALLITA:");
                Console.WriteLine(
                    "il bundle scritto non supera la verifica finale."
                );

                return 1;
            }

            Console.WriteLine();
            Console.WriteLine("============================================================");
            Console.WriteLine("PATCH COMPLETATA CON SUCCESSO");
            Console.WriteLine("============================================================");
            Console.WriteLine($"TMP elaborati: {targetTMP.Length}");
            Console.WriteLine($"IMAGE modificati: {totalModified}/{expectedImages}");
            Console.WriteLine("VERIFICA POST-SCRITTURA: PASS");

            return 0;
        }
        catch (Exception ex)
        {
            Console.WriteLine();
            Console.WriteLine("ERRORE scrittura/patch:");
            Console.WriteLine(ex);
            return 1;
        }
        finally
        {
            SafeReleaseAssetsTools();
        }
    }


    // ========================================================
    // SAFE BUNDLE REPLACE
    // ========================================================

    static bool ReplaceBundleWithRetry(
        string tempPath,
        string bundlePath)
    {
        const int maxAttempts = 10;

        for (int attempt = 1; attempt <= maxAttempts; attempt++)
        {
            try
            {
                File.Replace(
                    tempPath,
                    bundlePath,
                    null,
                    true
                );

                return true;
            }
            catch (PlatformNotSupportedException)
            {
                break;
            }
            catch (IOException)
            {
                if (attempt == maxAttempts)
                    break;

                Thread.Sleep(250);
            }
            catch (UnauthorizedAccessException)
            {
                if (attempt == maxAttempts)
                    break;

                Thread.Sleep(250);
            }
        }

        for (int attempt = 1; attempt <= maxAttempts; attempt++)
        {
            try
            {
                if (!File.Exists(tempPath))
                    return false;

                File.Copy(
                    tempPath,
                    bundlePath,
                    true
                );

                File.Delete(tempPath);

                return true;
            }
            catch (IOException)
            {
                if (attempt == maxAttempts)
                    break;

                Thread.Sleep(250);
            }
            catch (UnauthorizedAccessException)
            {
                if (attempt == maxAttempts)
                    break;

                Thread.Sleep(250);
            }
        }

        return false;
    }


    // ========================================================
    // VERIFY MODE
    // ========================================================

    static int RunVerify()
    {
        string bundlePath =
            @"F:\SteamLibrary\steamapps\common\東京サイコデミック\TOKYO_PSYCHODEMIC_Data\StreamingAssets\AssetBundles\fd321a81826f968a8c8086d118ed88bb";

        long[] targetTMP =
        {
            -5794335730920407933,
            2164585838490730081
        };

        Console.WriteLine("============================================================");
        Console.WriteLine("VERIFY FINAL BUNDLE");
        Console.WriteLine("============================================================");
        Console.WriteLine();
        Console.WriteLine("Bundle:");
        Console.WriteLine(bundlePath);
        Console.WriteLine();

        bool result = VerifyBundle(
            bundlePath,
            targetTMP,
            true
        );

        Console.WriteLine();
        Console.WriteLine("============================================================");
        Console.WriteLine("VERIFICA COMPLETATA");
        Console.WriteLine("============================================================");

        if (result)
        {
            Console.WriteLine("RISULTATO: PASS");
            return 0;
        }

        Console.WriteLine("RISULTATO: FAIL");
        return 1;
    }


    // ========================================================
    // VERIFY ARBITRARY BUNDLE
    // ========================================================

    static bool VerifyBundle(
        string bundlePath,
        long[] targetTMP,
        bool verbose)
    {
        AssetsManager? verifyAm = null;
        BundleFileInstance? verifyBundle = null;
        AssetsFileInstance? verifyAssetsInst = null;

        try
        {
            verifyAm = new AssetsManager();

            verifyBundle =
                verifyAm.LoadBundleFile(
                    bundlePath,
                    true
                );

            int assetsIndex = -1;

            for (
                int i = 0;
                i <
                verifyBundle.file.BlockAndDirInfo.DirectoryInfos.Count;
                i++
            )
            {
                try
                {
                    if (
                        verifyBundle.file.IsAssetsFile(i)
                    )
                    {
                        assetsIndex = i;
                        break;
                    }
                }
                catch
                {
                }
            }

            if (assetsIndex < 0)
            {
                Console.WriteLine(
                    "VERIFY: AssetsFile non trovato."
                );

                return false;
            }

            verifyAssetsInst =
                verifyAm.LoadAssetsFileFromBundle(
                    verifyBundle,
                    assetsIndex,
                    false
                );

            AssetsFile verifyAssets =
                verifyAssetsInst.file;

            if (verbose)
            {
                Console.WriteLine(
                    "Bundle loaded."
                );

                Console.WriteLine(
                    $"Unity: {verifyAssets.Metadata.UnityVersion}"
                );

                Console.WriteLine();
            }

            bool[] tmpOK =
                new bool[targetTMP.Length];

            for (
                int i = 0;
                i < targetTMP.Length;
                i++
            )
            {
                long tmpPathID =
                    targetTMP[i];

                if (verbose)
                {
                    Console.WriteLine(
                        "============================================================"
                    );

                    Console.WriteLine(
                        $"TMP TARGET [{i + 1}/{targetTMP.Length}]: {tmpPathID}"
                    );

                    Console.WriteLine(
                        "============================================================"
                    );
                }

                AssetFileInfo? tmpInfo =
                    FindAssetInAssetsFile(
                        verifyAssets,
                        tmpPathID
                    );

                if (tmpInfo == null)
                {
                    Console.WriteLine(
                        "TMP NON TROVATO."
                    );

                    continue;
                }

                AssetFileInfo? tmpGOInfo =
                    FindOwnerGameObjectInAssets(
                        verifyAm,
                        verifyAssetsInst,
                        verifyAssets,
                        tmpPathID
                    );

                if (tmpGOInfo == null)
                {
                    Console.WriteLine(
                        "GameObject TMP NON TROVATO."
                    );

                    continue;
                }

                long tmpTransformID =
                    FindTransformPathIDInAssets(
                        verifyAm,
                        verifyAssetsInst,
                        verifyAssets,
                        tmpGOInfo
                    );

                if (tmpTransformID == 0)
                {
                    Console.WriteLine(
                        "Transform TMP NON TROVATO."
                    );

                    continue;
                }

                AssetFileInfo? tmpTransformInfo =
                    FindAssetInAssetsFile(
                        verifyAssets,
                        tmpTransformID
                    );

                if (tmpTransformInfo == null)
                    continue;

                dynamic tmpTransform =
                    verifyAm.GetBaseField(
                        verifyAssetsInst,
                        tmpTransformInfo
                    );

                long fatherTransformID =
                    ReadLong(
                        tmpTransform[
                            "m_Father"
                        ]["m_PathID"]
                    );

                AssetFileInfo? fatherTransformInfo =
                    FindAssetInAssetsFile(
                        verifyAssets,
                        fatherTransformID
                    );

                if (fatherTransformInfo == null)
                    continue;

                dynamic fatherTransform =
                    verifyAm.GetBaseField(
                        verifyAssetsInst,
                        fatherTransformInfo
                    );

                long fatherGOID =
                    ReadLong(
                        fatherTransform[
                            "m_GameObject"
                        ]["m_PathID"]
                    );

                AssetFileInfo? fatherGOInfo =
                    FindAssetInAssetsFile(
                        verifyAssets,
                        fatherGOID
                    );

                if (fatherGOInfo == null)
                    continue;

                dynamic fatherGO =
                    verifyAm.GetBaseField(
                        verifyAssetsInst,
                        fatherGOInfo
                    );

                if (verbose)
                {
                    Console.WriteLine(
                        $"InteractCharacter = {SafeString(fatherGO, "m_Name")}"
                    );

                    Console.WriteLine();
                    Console.WriteLine(
                        "PARENT IMAGE:"
                    );
                }

                bool parentOK =
                    VerifyParentImage(
                        verifyAm,
                        verifyAssetsInst,
                        verifyAssets,
                        fatherGO,
                        verbose
                    );

                bool outlineOK =
                    VerifyOutlineImage(
                        verifyAm,
                        verifyAssetsInst,
                        verifyAssets,
                        fatherTransform,
                        verbose
                    );

                tmpOK[i] =
                    parentOK &&
                    outlineOK;

                Console.WriteLine();
            }

            bool allOK = true;

            for (
                int i = 0;
                i < tmpOK.Length;
                i++
            )
            {
                if (!tmpOK[i])
                    allOK = false;
            }

            if (verbose)
            {
                Console.WriteLine(
                    "------------------------------------------------------------"
                );

                if (allOK)
                {
                    Console.WriteLine(
                        "VERIFY: PASS"
                    );

                    Console.WriteLine(
                        "Tutti i TMP target hanno entrambi gli Image disabilitati."
                    );
                }
                else
                {
                    Console.WriteLine(
                        "VERIFY: FAIL"
                    );
                }
            }

            return allOK;
        }
        catch (Exception ex)
        {
            Console.WriteLine();
            Console.WriteLine(
                "VERIFY ERRORE:"
            );
            Console.WriteLine(ex);

            return false;
        }
        finally
        {
            try
            {
                if (
                    verifyAm != null &&
                    verifyBundle != null
                )
                {
                    verifyAm.UnloadBundleFile(
                        verifyBundle
                    );
                }
                else if (
                    verifyAm != null
                )
                {
                    verifyAm.UnloadAll();
                }
            }
            catch
            {
                try
                {
                    verifyAm?.UnloadAll();
                }
                catch
                {
                }
            }

            verifyAssetsInst = null;
            verifyBundle = null;
            verifyAm = null;

            GC.Collect();
            GC.WaitForPendingFinalizers();
        }
    }


    // ========================================================
    // VERIFY PARENT IMAGE
    // ========================================================

    static bool VerifyParentImage(
        AssetsManager verifyAm,
        AssetsFileInstance verifyAssetsInst,
        AssetsFile verifyAssets,
        dynamic go,
        bool verbose)
    {
        dynamic components;

        try
        {
            components =
                go["m_Component"];
        }
        catch
        {
            return false;
        }

        if (
            components == null ||
            components.Children.Count == 0
        )
        {
            return false;
        }

        dynamic array =
            components.Children[0];

        foreach (
            dynamic pair
            in array.Children
        )
        {
            if (
                pair.Children.Count == 0
            )
                continue;

            dynamic ptr =
                pair.Children[0];

            if (
                ptr.Children.Count < 2
            )
                continue;

            long componentID =
                ReadLong(
                    ptr.Children[1]
                );

            AssetFileInfo? info =
                FindAssetInAssetsFile(
                    verifyAssets,
                    componentID
                );

            if (info == null)
                continue;

            if (
                info.TypeId
                !=
                (int)AssetClassID.MonoBehaviour
            )
                continue;

            dynamic component =
                verifyAm.GetBaseField(
                    verifyAssetsInst,
                    info
                );

            if (
                GetScriptClassNameForAssets(
                    verifyAm,
                    verifyAssetsInst,
                    verifyAssets,
                    component
                )
                !=
                "Image"
            )
                continue;

            if (
                GetScriptNamespaceForAssets(
                    verifyAm,
                    verifyAssetsInst,
                    verifyAssets,
                    component
                )
                !=
                "UnityEngine.UI"
            )
                continue;

            bool enabled = true;

            try
            {
                enabled =
                    component["m_Enabled"].AsBool;
            }
            catch
            {
            }

            if (verbose)
            {
                Console.WriteLine(
                    $"  Image PathID = {componentID}"
                );

                Console.WriteLine(
                    $"  m_Enabled = {enabled}"
                );

                Console.WriteLine(
                    $"  m_Color.a = {ReadAlpha(component)}"
                );
            }

            return !enabled;
        }

        return false;
    }


    // ========================================================
    // VERIFY OUTLINE IMAGE
    // ========================================================

    static bool VerifyOutlineImage(
        AssetsManager verifyAm,
        AssetsFileInstance verifyAssetsInst,
        AssetsFile verifyAssets,
        dynamic fatherTransform,
        bool verbose)
    {
        dynamic children;

        try
        {
            children =
                fatherTransform[
                    "m_Children"
                ];
        }
        catch
        {
            return false;
        }

        if (
            children == null ||
            children.Children.Count == 0
        )
        {
            return false;
        }

        dynamic childArray =
            children.Children[0];

        for (
            int i = 0;
            i < childArray.Children.Count;
            i++
        )
        {
            dynamic childPtr =
                childArray.Children[i];

            if (
                childPtr.Children.Count < 2
            )
                continue;

            long childTransformID =
                ReadLong(
                    childPtr.Children[1]
                );

            AssetFileInfo? childTransformInfo =
                FindAssetInAssetsFile(
                    verifyAssets,
                    childTransformID
                );

            if (childTransformInfo == null)
                continue;

            dynamic childTransform =
                verifyAm.GetBaseField(
                    verifyAssetsInst,
                    childTransformInfo
                );

            long childGOID =
                ReadLong(
                    childTransform[
                        "m_GameObject"
                    ]["m_PathID"]
                );

            AssetFileInfo? childGOInfo =
                FindAssetInAssetsFile(
                    verifyAssets,
                    childGOID
                );

            if (childGOInfo == null)
                continue;

            dynamic childGO =
                verifyAm.GetBaseField(
                    verifyAssetsInst,
                    childGOInfo
                );

            string childName =
                SafeString(
                    childGO,
                    "m_Name"
                );

            if (
                childName
                !=
                "OutlineImage"
            )
                continue;

            if (verbose)
            {
                Console.WriteLine();
                Console.WriteLine(
                    "OUTLINE IMAGE:"
                );
            }

            return VerifyParentImage(
                verifyAm,
                verifyAssetsInst,
                verifyAssets,
                childGO,
                verbose
            );
        }

        return false;
    }


    // ========================================================
    // PATCH PARENT IMAGE
    // ========================================================

    static bool PatchFirstImage(
        dynamic go,
        string label)
    {
        dynamic components;

        try
        {
            components =
                go["m_Component"];
        }
        catch
        {
            return false;
        }

        if (
            components == null ||
            components.Children.Count == 0
        )
        {
            return false;
        }

        dynamic array =
            components.Children[0];

        for (
            int i = 0;
            i < array.Children.Count;
            i++
        )
        {
            dynamic pair =
                array.Children[i];

            if (
                pair.Children.Count == 0
            )
                continue;

            dynamic ptr =
                pair.Children[0];

            if (
                ptr.Children.Count < 2
            )
                continue;

            long componentID =
                ReadLong(
                    ptr.Children[1]
                );

            AssetFileInfo? info =
                FindAsset(
                    componentID
                );

            if (info == null)
                continue;

            if (
                info.TypeId
                !=
                (int)AssetClassID.MonoBehaviour
            )
            {
                continue;
            }

            dynamic component =
                am!.GetBaseField(
                    assetsInst,
                    info
                );

            if (
                GetScriptClassName(component)
                !=
                "Image"
            )
            {
                continue;
            }

            if (
                GetScriptNamespace(component)
                !=
                "UnityEngine.UI"
            )
            {
                continue;
            }

            bool oldEnabled =
                true;

            try
            {
                oldEnabled =
                    component[
                        "m_Enabled"
                    ].AsBool;
            }
            catch
            {
            }

            Console.WriteLine(
                $"{label}: Image PathID = {componentID}"
            );

            Console.WriteLine(
                $"  OLD m_Enabled = {oldEnabled}"
            );

            component[
                "m_Enabled"
            ].AsBool = false;

            Console.WriteLine(
                "  NEW m_Enabled = False"
            );

            info.Replacer =
                new ContentReplacerFromBuffer(
                    component.WriteToByteArray()
                );

            return true;
        }

        return false;
    }


    // ========================================================
    // PATCH OUTLINE IMAGE
    // ========================================================

    static bool PatchOutlineImage(
        dynamic fatherTransform)
    {
        dynamic children;

        try
        {
            children =
                fatherTransform[
                    "m_Children"
                ];
        }
        catch
        {
            return false;
        }

        if (
            children == null ||
            children.Children.Count == 0
        )
        {
            return false;
        }

        dynamic childArray =
            children.Children[0];

        for (
            int i = 0;
            i < childArray.Children.Count;
            i++
        )
        {
            dynamic childPtr =
                childArray.Children[i];

            if (
                childPtr.Children.Count < 2
            )
                continue;

            long childTransformID =
                ReadLong(
                    childPtr.Children[1]
                );

            AssetFileInfo? childTransformInfo =
                FindAsset(
                    childTransformID
                );

            if (
                childTransformInfo == null
            )
                continue;

            dynamic childTransform =
                am!.GetBaseField(
                    assetsInst,
                    childTransformInfo
                );

            long childGOID =
                ReadLong(
                    childTransform[
                        "m_GameObject"
                    ]["m_PathID"]
                );

            AssetFileInfo? childGOInfo =
                FindAsset(
                    childGOID
                );

            if (
                childGOInfo == null
            )
                continue;

            dynamic childGO =
                am.GetBaseField(
                    assetsInst,
                    childGOInfo
                );

            string childName =
                SafeString(
                    childGO,
                    "m_Name"
                );

            if (
                childName
                !=
                "OutlineImage"
            )
                continue;

            return PatchFirstImage(
                childGO,
                "OUTLINE IMAGE"
            );
        }

        return false;
    }


    // ========================================================
    // FIND ASSET
    // ========================================================

    static AssetFileInfo? FindAsset(
        long pathID)
    {
        return FindAssetInAssetsFile(
            assets!,
            pathID
        );
    }


    static AssetFileInfo? FindAssetInAssetsFile(
        AssetsFile targetAssets,
        long pathID)
    {
        foreach (
            AssetFileInfo info
            in targetAssets.AssetInfos
        )
        {
            if (
                info.PathId
                ==
                pathID
            )
            {
                return info;
            }
        }

        return null;
    }


    // ========================================================
    // FIND ASSETS FILE INDEX
    // ========================================================

    static int FindAssetsFileIndex()
    {
        for (
            int i = 0;
            i <
            bundleInst!
                .file
                .BlockAndDirInfo
                .DirectoryInfos
                .Count;
            i++
        )
        {
            try
            {
                if (
                    bundleInst
                        .file
                        .IsAssetsFile(i)
                )
                {
                    return i;
                }
            }
            catch
            {
            }
        }

        return -1;
    }


    // ========================================================
    // FIND OWNER GAMEOBJECT
    // ========================================================

    static AssetFileInfo? FindOwnerGameObject(
        long componentPathID)
    {
        return FindOwnerGameObjectInAssets(
            am!,
            assetsInst!,
            assets!,
            componentPathID
        );
    }


    static AssetFileInfo? FindOwnerGameObjectInAssets(
        AssetsManager manager,
        AssetsFileInstance fileInstance,
        AssetsFile targetAssets,
        long componentPathID)
    {
        foreach (
            AssetFileInfo info
            in targetAssets.AssetInfos
        )
        {
            if (
                info.TypeId
                !=
                (int)AssetClassID.GameObject
            )
            {
                continue;
            }

            dynamic go;

            try
            {
                go =
                    manager.GetBaseField(
                        fileInstance,
                        info
                    );
            }
            catch
            {
                continue;
            }

            dynamic components;

            try
            {
                components =
                    go["m_Component"];
            }
            catch
            {
                continue;
            }

            if (
                components == null ||
                components.Children.Count == 0
            )
            {
                continue;
            }

            dynamic array =
                components.Children[0];

            for (
                int i = 0;
                i < array.Children.Count;
                i++
            )
            {
                dynamic pair =
                    array.Children[i];

                if (
                    pair.Children.Count == 0
                )
                    continue;

                dynamic ptr =
                    pair.Children[0];

                if (
                    ptr.Children.Count < 2
                )
                    continue;

                long pathID =
                    ReadLong(
                        ptr.Children[1]
                    );

                if (
                    pathID
                    ==
                    componentPathID
                )
                {
                    return info;
                }
            }
        }

        return null;
    }


    // ========================================================
    // FIND TRANSFORM
    // ========================================================

    static long FindTransformPathID(
        AssetFileInfo goInfo)
    {
        return FindTransformPathIDInAssets(
            am!,
            assetsInst!,
            assets!,
            goInfo
        );
    }


    static long FindTransformPathIDInAssets(
        AssetsManager manager,
        AssetsFileInstance fileInstance,
        AssetsFile targetAssets,
        AssetFileInfo goInfo)
    {
        dynamic go =
            manager.GetBaseField(
                fileInstance,
                goInfo
            );

        dynamic components =
            go["m_Component"];

        if (
            components == null ||
            components.Children.Count == 0
        )
        {
            return 0;
        }

        dynamic array =
            components.Children[0];

        for (
            int i = 0;
            i < array.Children.Count;
            i++
        )
        {
            dynamic pair =
                array.Children[i];

            if (
                pair.Children.Count == 0
            )
                continue;

            dynamic ptr =
                pair.Children[0];

            if (
                ptr.Children.Count < 2
            )
                continue;

            long pathID =
                ReadLong(
                    ptr.Children[1]
                );

            AssetFileInfo? info =
                FindAssetInAssetsFile(
                    targetAssets,
                    pathID
                );

            if (info == null)
                continue;

            if (
                info.TypeId == 4
                ||
                info.TypeId == 224
            )
            {
                return pathID;
            }
        }

        return 0;
    }


    // ========================================================
    // SCRIPT CLASS
    // ========================================================

    static string GetScriptClassName(
        dynamic mono)
    {
        return GetScriptClassNameForAssets(
            am!,
            assetsInst!,
            assets!,
            mono
        );
    }


    static string GetScriptClassNameForAssets(
        AssetsManager manager,
        AssetsFileInstance fileInstance,
        AssetsFile targetAssets,
        dynamic mono)
    {
        try
        {
            long pathID =
                ReadLong(
                    mono[
                        "m_Script"
                    ]["m_PathID"]
                );

            AssetFileInfo? info =
                FindAssetInAssetsFile(
                    targetAssets,
                    pathID
                );

            if (info == null)
                return "";

            dynamic script =
                manager.GetBaseField(
                    fileInstance,
                    info
                );

            return script[
                "m_ClassName"
            ].AsString;
        }
        catch
        {
            return "";
        }
    }


    // ========================================================
    // SCRIPT NAMESPACE
    // ========================================================

    static string GetScriptNamespace(
        dynamic mono)
    {
        return GetScriptNamespaceForAssets(
            am!,
            assetsInst!,
            assets!,
            mono
        );
    }


    static string GetScriptNamespaceForAssets(
        AssetsManager manager,
        AssetsFileInstance fileInstance,
        AssetsFile targetAssets,
        dynamic mono)
    {
        try
        {
            long pathID =
                ReadLong(
                    mono[
                        "m_Script"
                    ]["m_PathID"]
                );

            AssetFileInfo? info =
                FindAssetInAssetsFile(
                    targetAssets,
                    pathID
                );

            if (info == null)
                return "";

            dynamic script =
                manager.GetBaseField(
                    fileInstance,
                    info
                );

            return script[
                "m_Namespace"
            ].AsString;
        }
        catch
        {
            return "";
        }
    }


    // ========================================================
    // SAFE RELEASE ASSETS TOOLS
    // ========================================================

    static void SafeReleaseAssetsTools()
    {
        try
        {
            if (
                am != null
                &&
                bundleInst != null
            )
            {
                am.UnloadBundleFile(
                    bundleInst
                );
            }
            else if (
                am != null
            )
            {
                am.UnloadAll();
            }
        }
        catch
        {
            try
            {
                am?.UnloadAll();
            }
            catch
            {
            }
        }

        assets =
            null;

        assetsInst =
            null;

        bundleInst =
            null;

        am =
            null;
    }


    // ========================================================
    // READ LONG
    // ========================================================

    static long ReadLong(
        dynamic field)
    {
        try
        {
            return field.AsLong;
        }
        catch
        {
        }

        try
        {
            return Convert.ToInt64(
                field.Value
            );
        }
        catch
        {
        }

        return 0;
    }


    // ========================================================
    // SAFE STRING
    // ========================================================

    static string SafeString(
        dynamic field,
        string name)
    {
        try
        {
            return field[
                name
            ].AsString;
        }
        catch
        {
            return "";
        }
    }


    // ========================================================
    // READ ALPHA
    // ========================================================

    static float ReadAlpha(
        dynamic image)
    {
        try
        {
            return image[
                "m_Color"
            ]["a"].AsFloat;
        }
        catch
        {
            return -1;
        }
    }
}