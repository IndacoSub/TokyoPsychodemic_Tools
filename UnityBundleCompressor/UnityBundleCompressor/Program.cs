using AssetsTools.NET;
using System.Diagnostics;
using System.Security.Cryptography;

namespace UnityBundleCompressor;

internal static class Program
{
	private const bool NormalizeLz4BeforeLzma = true;
	private const bool Lz4Enabled = false;

	// Validazione completa:
	// - struttura UnityFS
	// - block table
	// - dimensioni
	// - SHA-256 data area
	// - SHA-256 singole entry
	// - confronto metadata directory
	// - confronto byte-per-byte data area
	private const bool DeepValidation = true;

	private const int IoBufferSize = 1024 * 1024;
	private const int ExactCompareBufferSize = 1024 * 1024;

	private static readonly object ConsoleLock = new object();

	private static int Main(string[] args)
	{
		Console.OutputEncoding = System.Text.Encoding.UTF8;

		if (args.Length == 0 || HasFlag(args, "--help") || HasFlag(args, "-h"))
		{
			PrintUsage();
			return args.Length == 0 ? 1 : 0;
		}

		string? input = GetOption(args, "--input", "-i");
		string? output = GetOption(args, "--output", "-o");
		string compression = (GetOption(args, "--compression", "-c") ?? "lzma").Trim().ToLowerInvariant();

		// Forma compatta:
		// UnityBundleCompressor.exe input.bundle output.bundle
		if (input == null && output == null && args.Length >= 2 && !args[0].StartsWith('-') && !args[1].StartsWith('-'))
		{
			input = args[0];
			output = args[1];
		}

		if (string.IsNullOrWhiteSpace(input) || string.IsNullOrWhiteSpace(output))
		{
			Console.Error.WriteLine("[ERROR] Input and output are required.");
			PrintUsage();
			return 1;
		}

		if (compression != "lzma" && compression != "lz4")
		{
			Console.Error.WriteLine("[ERROR] Compression must be 'lzma' or 'lz4'.");
			return 1;
		}

		if (compression == "lz4" && !Lz4Enabled)
		{
			Console.Error.WriteLine("[ERROR] LZ4 support is implemented but currently disabled in this build.");
			Console.Error.WriteLine("[ERROR] Set Lz4Enabled = true in Program.cs to enable it.");
			return 2;
		}

		string inputPath = Path.GetFullPath(input);
		string outputPath = Path.GetFullPath(output);

		if (!File.Exists(inputPath))
		{
			Console.Error.WriteLine($"[ERROR] Input file does not exist: {inputPath}");
			return 1;
		}

		if (string.Equals(inputPath, outputPath, StringComparison.OrdinalIgnoreCase))
		{
			Console.Error.WriteLine("[ERROR] Input and output must be different files.");
			return 1;
		}

		try
		{
			return CompressBundle(inputPath, outputPath, compression);
		}
		catch (Exception ex)
		{
			Console.Error.WriteLine();
			Console.Error.WriteLine("[ERROR] Compression failed.");
			Console.Error.WriteLine(ex);
			return 1;
		}
	}

	private static int CompressBundle(string inputPath, string outputPath, string compression)
	{
		Stopwatch stopwatch = Stopwatch.StartNew();

		AssetBundleCompressionType compressionType = compression == "lzma" ? AssetBundleCompressionType.LZMA : AssetBundleCompressionType.LZ4;
		int processId = Process.GetCurrentProcess().Id;

		Log("============================================================");
		Log("Unity Bundle Compressor");
		Log("============================================================");
		Log($"PID         : {processId}");
		Log($"Input       : {inputPath}");
		Log($"Output      : {outputPath}");
		Log($"Compression : {compressionType}");
		Log($"Validation  : {(DeepValidation ? "FULL" : "BASIC")}");
		Log();

		string? outputDirectory = Path.GetDirectoryName(outputPath);

		if (!string.IsNullOrEmpty(outputDirectory))
		{
			Directory.CreateDirectory(outputDirectory);
		}

		FileInfo inputInfo = new FileInfo(inputPath);
		LoadedBundle? sourceBundle = null;
		string? normalizedPath = null;
		string? packedTempPath = null;

		try
		{
			// --------------------------------------------------------
			// STEP 1
			// --------------------------------------------------------

			Log("[1/6] Reading AssetBundle...");

			sourceBundle = OpenBundle(inputPath);

			AssetBundleFile bundle = sourceBundle.Bundle;

			PrintBundleInfo(bundle, "      ");

			ValidateUnityFsContainer(bundle, inputPath, "Input");

			AssetBundleCompressionType inputType = bundle.GetCompressionType();

			Log($"      Input compression: {inputType}");

			if (bundle.DataIsCompressed)
			{
				throw new InvalidOperationException("The input AssetBundle is already LZMA-compressed. This tool expects an uncompressed or LZ4 UnityFS bundle.");
			}

			// --------------------------------------------------------
			// STEP 2
			// --------------------------------------------------------

			if (compressionType == AssetBundleCompressionType.LZMA && inputType == AssetBundleCompressionType.LZ4 && NormalizeLz4BeforeLzma)
			{
				normalizedPath = CreateTempPath(outputPath, ".unpacked.tmp");

				Log();
				Log("[2/6] Normalizing LZ4 input...");
				Log($"      Temporary : {normalizedPath}");

				using (FileStream normalizedStream = new FileStream(normalizedPath, FileMode.Create, FileAccess.ReadWrite, FileShare.None, IoBufferSize, FileOptions.SequentialScan))
				using (AssetsFileWriter normalizedWriter = new AssetsFileWriter(normalizedStream))
				{
					// sourceBundle DEVE essere aperto qui.
					bundle.Unpack(normalizedWriter);

					normalizedWriter.Flush();
					normalizedStream.Flush(true);
				}

				Log("      LZ4 data expanded successfully.");

				sourceBundle.Dispose();
				sourceBundle = null;

				sourceBundle = OpenBundle(normalizedPath);
				bundle = sourceBundle.Bundle;

				Log("      Normalized bundle:");

				PrintBundleInfo(bundle, "        ");

				ValidateUnityFsContainer(bundle, normalizedPath, "Normalized input");

				if (bundle.DataIsCompressed)
				{
					throw new InvalidDataException("The normalized bundle is still reported as compressed.");
				}

				if (bundle.GetCompressionType() != AssetBundleCompressionType.None)
				{
					throw new InvalidDataException("The normalized bundle is not actually uncompressed.");
				}
			}
			else
			{
				Log();
				Log("[2/6] No normalization required.");
			}

			// --------------------------------------------------------
			// STEP 3
			// --------------------------------------------------------

			Log();
			Log("[3/6] Creating source integrity snapshot...");

			BundleSnapshot sourceSnapshot = CreateSnapshot(sourceBundle.Bundle, "Source");

			PrintSnapshot(sourceSnapshot, "      ");

			// --------------------------------------------------------
			// STEP 4
			// --------------------------------------------------------

			Log();
			Log($"[4/6] Packing with {compressionType}...");

			packedTempPath = CreateTempPath(outputPath, ".packing.tmp");

			Log($"      Temporary output: {packedTempPath}");

			using (FileStream outputStream = new FileStream(packedTempPath, FileMode.Create, FileAccess.ReadWrite, FileShare.None, IoBufferSize, FileOptions.SequentialScan))
			using (AssetsFileWriter writer = new AssetsFileWriter(outputStream))
			{
				// sourceBundle resta vivo durante TUTTO Pack().
				sourceBundle.Bundle.Pack(writer, compressionType, true);

				writer.Flush();
				outputStream.Flush(true);
			}

			Log($"      Packed file created: {new FileInfo(packedTempPath).Length:N0} bytes");

			// --------------------------------------------------------
			// STEP 5
			// --------------------------------------------------------

			Log();
			Log("[5/6] Full output validation...");

			if (DeepValidation)
			{
				ValidateOutputCompletely(packedTempPath, compressionType, sourceBundle.Bundle, sourceSnapshot);
			}
			else
			{
				ValidateOutputBasic(packedTempPath, compressionType);
			}

			// --------------------------------------------------------
			// STEP 6
			// --------------------------------------------------------

			Log();
			Log("[6/6] Validation passed. Replacing destination...");

			File.Move(packedTempPath, outputPath, true);
			packedTempPath = null;

			Log("      Destination replaced successfully.");
		}
		finally
		{
			if (sourceBundle != null)
			{
				try
				{
					sourceBundle.Dispose();
				}
				catch
				{
					// Cleanup only.
				}
			}

			TryDeleteFile(normalizedPath);
			TryDeleteFile(packedTempPath);
		}

		stopwatch.Stop();

		if (!File.Exists(outputPath))
		{
			throw new FileNotFoundException("Output file was not created.", outputPath);
		}

		FileInfo outputInfo = new FileInfo(outputPath);

		Log();
		Log("============================================================");
		Log("COMPLETED");
		Log("============================================================");
		Log($"Input size      : {inputInfo.Length:N0} bytes");
		Log($"Output size     : {outputInfo.Length:N0} bytes");

		if (inputInfo.Length > 0)
		{
			double physicalRatio = (double)outputInfo.Length / inputInfo.Length * 100.0;
			double physicalReduction = 100.0 - physicalRatio;

			Log($"Physical ratio  : {physicalRatio:F4}%");
			Log($"Physical reduce : {physicalReduction:F4}%");
		}

		Log($"Elapsed         : {stopwatch.Elapsed.TotalSeconds:F2}s");
		Log($"Output          : {outputPath}");
		Log("============================================================");

		return 0;
	}

	// ============================================================
	// FULL VALIDATION
	// ============================================================

	private static void ValidateOutputCompletely(string outputPath, AssetBundleCompressionType expectedType, AssetBundleFile sourceBundle, BundleSnapshot sourceSnapshot)
	{
		Log();
		Log("      ---------------- FULL VALIDATION ----------------");

		using LoadedBundle packedBundle = OpenBundle(outputPath);

		AssetBundleFile bundle = packedBundle.Bundle;

		ValidateUnityFsContainer(bundle, outputPath, "Packed output");

		AssetBundleCompressionType actualType = bundle.GetCompressionType();

		Log($"      Compression detected : {actualType}");

		if (actualType != expectedType)
		{
			throw new InvalidDataException($"Generated bundle compression is '{actualType}', expected '{expectedType}'.");
		}

		if (expectedType == AssetBundleCompressionType.LZMA)
		{
			if (!bundle.DataIsCompressed)
			{
				throw new InvalidDataException("LZMA output is not reported as DataIsCompressed.");
			}

			ValidateAllBlockCompressionTypes(bundle, AssetBundleCompressionType.LZMA);
		}

		Log();
		Log("      [A] Output block table:");

		BlockStats outputBlocks = AnalyzeBlocks(bundle);

		PrintBlockStats(outputBlocks, "          ");

		if (expectedType == AssetBundleCompressionType.LZMA)
		{
			if (outputBlocks.DecompressedBytes != sourceSnapshot.DataAreaLength)
			{
				throw new InvalidDataException($"CRITICAL: LZMA declared decompressed payload size ({outputBlocks.DecompressedBytes:N0}) does not equal source data area ({sourceSnapshot.DataAreaLength:N0}).");
			}

			Log("          Declared decompressed payload size: MATCH");
		}

		Log();
		Log("      [B] Directory table:");

		ValidateDirectoryTable(bundle, outputBlocks, "Packed output");

		Log();
		Log("      [C] Physical file/header validation:");

		ValidatePhysicalFileSize(outputPath, bundle, "Packed output");

		// --------------------------------------------------------
		// Unpack output to an independent temporary UnityFS.
		// --------------------------------------------------------

		string roundtripPath = CreateTempPath(outputPath, ".roundtrip.tmp");

		try
		{
			Log();
			Log("      [D] Decompressing generated LZMA output...");

			using (FileStream unpackStream = new FileStream(roundtripPath, FileMode.Create, FileAccess.ReadWrite, FileShare.None, IoBufferSize, FileOptions.SequentialScan))
			using (AssetsFileWriter unpackWriter = new AssetsFileWriter(unpackStream))
			{
				bundle.Unpack(unpackWriter);

				unpackWriter.Flush();
				unpackStream.Flush(true);
			}

			FileInfo roundtripInfo = new FileInfo(roundtripPath);

			Log($"          Roundtrip file: {roundtripInfo.Length:N0} bytes");

			using LoadedBundle roundtripBundle = OpenBundle(roundtripPath);

			AssetBundleFile roundtrip = roundtripBundle.Bundle;

			Log("          Roundtrip UnityFS opened successfully.");

			ValidateUnityFsContainer(roundtrip, roundtripPath, "Roundtrip");

			AssetBundleCompressionType roundtripType = roundtrip.GetCompressionType();

			Log($"          Roundtrip compression: {roundtripType}");

			if (roundtripType != AssetBundleCompressionType.None)
			{
				throw new InvalidDataException("Roundtrip bundle is not uncompressed after LZMA decompression.");
			}

			if (roundtrip.DataIsCompressed)
			{
				throw new InvalidDataException("Roundtrip bundle still reports DataIsCompressed=true.");
			}

			ValidateAllBlockCompressionTypes(roundtrip, AssetBundleCompressionType.None);

			Log();
			Log("      [E] Creating roundtrip integrity snapshot...");

			BundleSnapshot roundtripSnapshot = CreateSnapshot(roundtrip, "Roundtrip");

			PrintSnapshot(roundtripSnapshot, "          ");

			Log();
			Log("      [F] Comparing source vs roundtrip metadata...");

			CompareSnapshots(sourceSnapshot, roundtripSnapshot);

			Log("          Metadata + directory hashes: MATCH");

			Log();
			Log("      [G] Comparing entire logical data area byte-by-byte...");

			ByteComparisonResult exactResult = CompareDataAreasExact(sourceBundle, roundtrip);

			Log($"          Compared bytes: {exactResult.ComparedBytes:N0}");

			if (!exactResult.AreEqual)
			{
				throw new InvalidDataException($"CRITICAL: source and roundtrip data areas differ. First mismatch at byte {exactResult.FirstMismatchOffset:N0}.");
			}

			Log("          Byte-for-byte comparison: EXACT MATCH");

			Log();
			Log("      [H] Final integrity result:");
			Log("          Source SHA-256    = " + sourceSnapshot.DataSha256);
			Log("          Roundtrip SHA-256 = " + roundtripSnapshot.DataSha256);

			if (!string.Equals(sourceSnapshot.DataSha256, roundtripSnapshot.DataSha256, StringComparison.OrdinalIgnoreCase))
			{
				throw new InvalidDataException("CRITICAL: SHA-256 mismatch.");
			}

			Log("          SHA-256: MATCH");

			Log();
			Log("      FULL VALIDATION: PASSED");
			Log("      The LZMA output decompresses to exactly the same logical bundle data as the source.");
			Log("      --------------------------------------------------");
		}
		finally
		{
			TryDeleteFile(roundtripPath);
		}
	}

	private static void ValidateOutputBasic(string outputPath, AssetBundleCompressionType expectedType)
	{
		using LoadedBundle verifyBundle = OpenBundle(outputPath);

		AssetBundleFile bundle = verifyBundle.Bundle;

		ValidateUnityFsContainer(bundle, outputPath, "Output");

		AssetBundleCompressionType actualType = bundle.GetCompressionType();

		if (actualType != expectedType)
		{
			throw new InvalidDataException($"Output compression is '{actualType}', expected '{expectedType}'.");
		}

		Log("      Basic validation: OK");
	}

	// ============================================================
	// SNAPSHOT
	// ============================================================

	private static BundleSnapshot CreateSnapshot(AssetBundleFile bundle, string label)
	{
		if (bundle.DataIsCompressed)
		{
			throw new InvalidOperationException($"Cannot create a logical data snapshot from compressed bundle '{label}'.");
		}

		Stream dataStream = bundle.DataReader.BaseStream;
		long originalPosition = bundle.DataReader.Position;

		try
		{
			long dataLength = dataStream.Length;

			if (dataLength < 0)
			{
				throw new InvalidDataException($"{label}: invalid data stream length.");
			}

			RangeProfile dataProfile = ProfileRange(dataStream, 0, dataLength);

			BundleSnapshot snapshot = new BundleSnapshot
			{
				Label = label,
				Signature = bundle.Header.Signature,
				Version = bundle.Header.Version,
				GenerationVersion = bundle.Header.GenerationVersion,
				EngineVersion = bundle.Header.EngineVersion,
				DataAreaLength = dataLength,
				DataSha256 = dataProfile.Sha256,
				ZeroByteCount = dataProfile.ZeroByteCount,
				DistinctByteValues = dataProfile.DistinctByteValues,
				MinimumByte = dataProfile.MinimumByte,
				MaximumByte = dataProfile.MaximumByte,
			};

			for (int i = 0; i < bundle.BlockAndDirInfo.DirectoryInfos.Count; i++)
			{
				AssetBundleDirectoryInfo info = bundle.BlockAndDirInfo.DirectoryInfos[i];
				long offset = Convert.ToInt64(info.Offset);
				long size = Convert.ToInt64(info.DecompressedSize);
				int flags = Convert.ToInt32(info.Flags);

				ValidateDirectoryRange(label, i, info.Name, offset, size, dataLength);

				string hash = ComputeSha256Range(dataStream, offset, size);

				snapshot.Entries.Add(new DirectorySnapshotEntry
				{
					Index = i,
					Name = info.Name ?? string.Empty,
					Offset = offset,
					Size = size,
					Flags = flags,
					Sha256 = hash,
				});
			}

			return snapshot;
		}
		finally
		{
			try
			{
				bundle.DataReader.Position = originalPosition;
			}
			catch
			{
				// Best effort.
			}
		}
	}

	private static void PrintSnapshot(BundleSnapshot snapshot, string prefix)
	{
		double zeroPercent = snapshot.DataAreaLength == 0 ? 0.0 : (double)snapshot.ZeroByteCount / snapshot.DataAreaLength * 100.0;

		Log($"{prefix}Signature          : {snapshot.Signature}");
		Log($"{prefix}Version            : {snapshot.Version}");
		Log($"{prefix}Generation         : {snapshot.GenerationVersion}");
		Log($"{prefix}Unity              : {snapshot.EngineVersion}");
		Log($"{prefix}Data area          : {snapshot.DataAreaLength:N0} bytes");
		Log($"{prefix}Data SHA-256       : {snapshot.DataSha256}");
		Log($"{prefix}Zero bytes         : {snapshot.ZeroByteCount:N0} ({zeroPercent:F4}%)");
		Log($"{prefix}Distinct byte vals : {snapshot.DistinctByteValues}/256");
		Log($"{prefix}Byte range         : 0x{snapshot.MinimumByte:X2} - 0x{snapshot.MaximumByte:X2}");
		Log($"{prefix}Directory entries  : {snapshot.Entries.Count}");

		foreach (DirectorySnapshotEntry entry in snapshot.Entries)
		{
			Log($"{prefix}  [{entry.Index}] {entry.Name}");
			Log($"{prefix}       Offset : {entry.Offset:N0}");
			Log($"{prefix}       Size   : {entry.Size:N0}");
			Log($"{prefix}       Flags  : 0x{entry.Flags:X8}");
			Log($"{prefix}       SHA256 : {entry.Sha256}");
		}
	}

	// ============================================================
	// BLOCK VALIDATION
	// ============================================================

	private static BlockStats AnalyzeBlocks(AssetBundleFile bundle)
	{
		long compressedBytes = 0;
		long decompressedBytes = 0;
		List<byte> compressionTypes = new List<byte>();
		AssetBundleBlockInfo[] blocks = bundle.BlockAndDirInfo.BlockInfos;

		for (int i = 0; i < blocks.Length; i++)
		{
			AssetBundleBlockInfo block = blocks[i];
			long compressed = Convert.ToInt64(block.CompressedSize);
			long decompressed = Convert.ToInt64(block.DecompressedSize);

			if (compressed < 0 || decompressed < 0)
			{
				throw new InvalidDataException($"Invalid block sizes at block {i}.");
			}

			compressedBytes += compressed;
			decompressedBytes += decompressed;

			byte type = block.GetCompressionType();

			compressionTypes.Add(type);
		}

		return new BlockStats
		{
			BlockCount = blocks.Length,
			CompressedBytes = compressedBytes,
			DecompressedBytes = decompressedBytes,
			CompressionTypes = compressionTypes,
		};
	}

	private static void PrintBlockStats(BlockStats stats, string prefix)
	{
		Log($"{prefix}Block count       : {stats.BlockCount}");
		Log($"{prefix}Compressed bytes  : {stats.CompressedBytes:N0}");
		Log($"{prefix}Decompressed bytes: {stats.DecompressedBytes:N0}");
		Log($"{prefix}Compression types : " + string.Join(", ", stats.CompressionTypes.Select(TypeToString)));

		if (stats.DecompressedBytes > 0)
		{
			double ratio = (double)stats.CompressedBytes / stats.DecompressedBytes * 100.0;

			Log($"{prefix}Payload ratio     : {ratio:F4}%");
			Log($"{prefix}Payload reduction : {100.0 - ratio:F4}%");

			if (ratio < 1.0)
			{
				Log($"{prefix}NOTE               : extremely high compression ratio.");
			}
		}
	}

	private static void ValidateAllBlockCompressionTypes(AssetBundleFile bundle, AssetBundleCompressionType expectedType)
	{
		byte expected = expectedType switch
		{
			AssetBundleCompressionType.None => 0,
			AssetBundleCompressionType.LZMA => 1,
			AssetBundleCompressionType.LZ4 => 2,
			AssetBundleCompressionType.LZ4Fast => 3,
			_ => throw new ArgumentOutOfRangeException(nameof(expectedType))
		};

		AssetBundleBlockInfo[] blocks = bundle.BlockAndDirInfo.BlockInfos;

		for (int i = 0; i < blocks.Length; i++)
		{
			byte actual = blocks[i].GetCompressionType();

			if (actual != expected)
			{
				throw new InvalidDataException($"Block {i} uses compression type {TypeToString(actual)} ({actual}), expected {TypeToString(expected)} ({expected}).");
			}
		}
	}

	// ============================================================
	// DIRECTORY VALIDATION
	// ============================================================

	private static void ValidateDirectoryTable(AssetBundleFile bundle, BlockStats blocks, string label)
	{
		long dataLength = blocks.DecompressedBytes;

		List<(long Start, long End, int Index)> ranges = new List<(long Start, long End, int Index)>();

		for (int i = 0; i < bundle.BlockAndDirInfo.DirectoryInfos.Count; i++)
		{
			AssetBundleDirectoryInfo entry = bundle.BlockAndDirInfo.DirectoryInfos[i];
			long offset = Convert.ToInt64(entry.Offset);
			long size = Convert.ToInt64(entry.DecompressedSize);

			ValidateDirectoryRange(label, i, entry.Name, offset, size, dataLength);

			if (size > 0)
			{
				ranges.Add((offset, checked(offset + size), i));
			}
		}

		ranges.Sort((a, b) => a.Start.CompareTo(b.Start));

		for (int i = 1; i < ranges.Count; i++)
		{
			var previous = ranges[i - 1];
			var current = ranges[i];

			if (current.Start < previous.End)
			{
				Log($"      WARNING: directory entries overlap: {previous.Index} and {current.Index}");
			}
		}

		Log($"      Directory ranges validated: {bundle.BlockAndDirInfo.DirectoryInfos.Count} entries.");
	}

	private static void ValidateDirectoryRange(string label, int index, string? name, long offset, long size, long dataLength)
	{
		if (offset < 0)
		{
			throw new InvalidDataException($"{label}: directory entry {index} '{name}' has negative offset.");
		}

		if (size < 0)
		{
			throw new InvalidDataException($"{label}: directory entry {index} '{name}' has negative size.");
		}

		long end;

		try
		{
			end = checked(offset + size);
		}
		catch (OverflowException)
		{
			throw new InvalidDataException($"{label}: directory entry {index} '{name}' range overflow.");
		}

		if (end > dataLength)
		{
			throw new InvalidDataException($"{label}: directory entry {index} '{name}' extends beyond data area. End={end:N0}, DataLength={dataLength:N0}.");
		}
	}

	// ============================================================
	// PHYSICAL CONTAINER VALIDATION
	// ============================================================

	private static void ValidateUnityFsContainer(AssetBundleFile bundle, string path, string label)
	{
		if (!string.Equals(bundle.Header.Signature, "UnityFS", StringComparison.Ordinal))
		{
			throw new NotSupportedException($"{label}: expected UnityFS, found '{bundle.Header.Signature}'.");
		}

		if (bundle.BlockAndDirInfo == null)
		{
			throw new InvalidDataException($"{label}: block/directory info is null.");
		}

		if (bundle.BlockAndDirInfo.BlockInfos == null)
		{
			throw new InvalidDataException($"{label}: block table is null.");
		}

		if (bundle.BlockAndDirInfo.DirectoryInfos == null)
		{
			throw new InvalidDataException($"{label}: directory table is null.");
		}

		if (bundle.BlockAndDirInfo.BlockInfos.Length == 0)
		{
			throw new InvalidDataException($"{label}: bundle contains zero blocks.");
		}

		FileInfo fileInfo = new FileInfo(path);

		if (!fileInfo.Exists)
		{
			throw new FileNotFoundException($"{label}: file disappeared during validation.", path);
		}

		long declaredSize = Convert.ToInt64(bundle.Header.FileStreamHeader.TotalFileSize);

		Log($"      {label} header total size : {declaredSize:N0}");
		Log($"      {label} physical size     : {fileInfo.Length:N0}");

		if (declaredSize != fileInfo.Length)
		{
			throw new InvalidDataException($"{label}: UnityFS header declares {declaredSize:N0} bytes, actual file is {fileInfo.Length:N0} bytes.");
		}

		Log($"      {label} physical size check: OK");
	}

	private static void ValidatePhysicalFileSize(string path, AssetBundleFile bundle, string label)
	{
		FileInfo info = new FileInfo(path);
		long declared = Convert.ToInt64(bundle.Header.FileStreamHeader.TotalFileSize);

		Log($"          Header total size : {declared:N0}");
		Log($"          Actual file size   : {info.Length:N0}");

		if (declared != info.Length)
		{
			throw new InvalidDataException($"{label}: header/file size mismatch.");
		}

		Log("          Header/file size : MATCH");
	}

	// ============================================================
	// SNAPSHOT COMPARISON
	// ============================================================

	private static void CompareSnapshots(BundleSnapshot source, BundleSnapshot roundtrip)
	{
		if (!string.Equals(source.Signature, roundtrip.Signature, StringComparison.Ordinal))
		{
			throw new InvalidDataException("Signature mismatch.");
		}

		if (source.Version != roundtrip.Version)
		{
			throw new InvalidDataException($"Version mismatch: source={source.Version}, roundtrip={roundtrip.Version}.");
		}

		if (!string.Equals(source.GenerationVersion, roundtrip.GenerationVersion, StringComparison.Ordinal))
		{
			throw new InvalidDataException("GenerationVersion mismatch.");
		}

		if (!string.Equals(source.EngineVersion, roundtrip.EngineVersion, StringComparison.Ordinal))
		{
			throw new InvalidDataException($"Engine version mismatch: source='{source.EngineVersion}', roundtrip='{roundtrip.EngineVersion}'.");
		}

		if (source.DataAreaLength != roundtrip.DataAreaLength)
		{
			throw new InvalidDataException($"Data area size mismatch: source={source.DataAreaLength:N0}, roundtrip={roundtrip.DataAreaLength:N0}.");
		}

		if (!string.Equals(source.DataSha256, roundtrip.DataSha256, StringComparison.OrdinalIgnoreCase))
		{
			throw new InvalidDataException("Entire data area SHA-256 mismatch.");
		}

		if (source.Entries.Count != roundtrip.Entries.Count)
		{
			throw new InvalidDataException($"Directory count mismatch: source={source.Entries.Count}, roundtrip={roundtrip.Entries.Count}.");
		}

		for (int i = 0; i < source.Entries.Count; i++)
		{
			DirectorySnapshotEntry a = source.Entries[i];
			DirectorySnapshotEntry b = roundtrip.Entries[i];

			if (!string.Equals(a.Name, b.Name, StringComparison.Ordinal))
			{
				throw new InvalidDataException($"Directory entry {i} name mismatch: '{a.Name}' != '{b.Name}'.");
			}

			if (a.Size != b.Size)
			{
				throw new InvalidDataException($"Entry '{a.Name}' size mismatch: {a.Size:N0} != {b.Size:N0}.");
			}

			if (a.Flags != b.Flags)
			{
				throw new InvalidDataException($"Entry '{a.Name}' flags mismatch: 0x{a.Flags:X8} != 0x{b.Flags:X8}.");
			}

			if (!string.Equals(a.Sha256, b.Sha256, StringComparison.OrdinalIgnoreCase))
			{
				throw new InvalidDataException($"Entry '{a.Name}' SHA-256 mismatch.");
			}

			// L'offset non deve necessariamente essere usato come
			// identità semantica, ma nel nostro caso AssetsTools.NET
			// lo preserva. Se cambia, segnaliamo senza trasformarlo
			// automaticamente in un errore.
			if (a.Offset != b.Offset)
			{
				Log($"          WARNING: entry '{a.Name}' offset changed: {a.Offset:N0} -> {b.Offset:N0}");
			}
		}
	}

	// ============================================================
	// EXACT BYTE COMPARISON
	// ============================================================

	private static ByteComparisonResult CompareDataAreasExact(AssetBundleFile source, AssetBundleFile roundtrip)
	{
		if (source.DataIsCompressed || roundtrip.DataIsCompressed)
		{
			throw new InvalidOperationException("Exact data comparison requires uncompressed bundles.");
		}

		Stream a = source.DataReader.BaseStream;
		Stream b = roundtrip.DataReader.BaseStream;

		if (a.Length != b.Length)
		{
			throw new InvalidDataException($"Data stream lengths differ before exact comparison: {a.Length:N0} != {b.Length:N0}.");
		}

		long originalA = source.DataReader.Position;
		long originalB = roundtrip.DataReader.Position;

		byte[] bufferA = new byte[ExactCompareBufferSize];
		byte[] bufferB = new byte[ExactCompareBufferSize];

		long totalCompared = 0;

		try
		{
			a.Position = 0;
			b.Position = 0;

			long remaining = a.Length;

			while (remaining > 0)
			{
				int wanted = (int)Math.Min(remaining, bufferA.Length);
				int readA = ReadExactlyOrEof(a, bufferA, wanted);
				int readB = ReadExactlyOrEof(b, bufferB, wanted);

				if (readA != readB)
				{
					return new ByteComparisonResult
					{
						AreEqual = false,
						ComparedBytes = totalCompared,
						FirstMismatchOffset = totalCompared,
					};
				}

				if (readA == 0)
				{
					break;
				}

				for (int i = 0; i < readA; i++)
				{
					if (bufferA[i] != bufferB[i])
					{
						return new ByteComparisonResult
						{
							AreEqual = false,
							ComparedBytes = totalCompared + i,
							FirstMismatchOffset = totalCompared + i,
						};
					}
				}

				totalCompared += readA;
				remaining -= readA;
			}

			return new ByteComparisonResult
			{
				AreEqual = true,
				ComparedBytes = totalCompared,
				FirstMismatchOffset = -1,
			};
		}
		finally
		{
			try
			{
				source.DataReader.Position = originalA;
			}
			catch
			{
				// Best effort.
			}

			try
			{
				roundtrip.DataReader.Position = originalB;
			}
			catch
			{
				// Best effort.
			}
		}
	}

	private static int ReadExactlyOrEof(Stream stream, byte[] buffer, int requested)
	{
		int total = 0;

		while (total < requested)
		{
			int read = stream.Read(buffer, total, requested - total);

			if (read <= 0)
			{
				break;
			}

			total += read;
		}

		return total;
	}

	// ============================================================
	// HASHING / PROFILING
	// ============================================================

	private static RangeProfile ProfileRange(Stream stream, long offset, long length)
	{
		if (offset < 0)
			throw new ArgumentOutOfRangeException(nameof(offset));

		if (length < 0)
			throw new ArgumentOutOfRangeException(nameof(length));

		if (offset > stream.Length || length > stream.Length - offset)
		{
			throw new InvalidDataException("Requested hash range exceeds stream bounds.");
		}

		long originalPosition = stream.Position;

		try
		{
			stream.Position = offset;

			using SHA256 sha = SHA256.Create();

			byte[] buffer = new byte[IoBufferSize];
			bool[] seen = new bool[256];

			long remaining = length;
			long zeroCount = 0;
			int distinct = 0;
			int min = 255;
			int max = 0;

			while (remaining > 0)
			{
				int requested = (int)Math.Min(remaining, buffer.Length);

				int read = stream.Read(buffer, 0, requested);

				if (read <= 0)
				{
					throw new EndOfStreamException("Unexpected end of stream while hashing.");
				}

				sha.TransformBlock(buffer, 0, read, buffer, 0);

				for (int i = 0; i < read; i++)
				{
					byte value = buffer[i];

					if (value == 0)
						zeroCount++;

					if (!seen[value])
					{
						seen[value] = true;
						distinct++;
					}

					if (value < min)
						min = value;

					if (value > max)
						max = value;
				}

				remaining -= read;
			}

			sha.TransformFinalBlock(Array.Empty<byte>(), 0, 0);

			string hash = ToHex(sha.Hash!);

			return new RangeProfile
			{
				Length = length,
				Sha256 = hash,
				ZeroByteCount = zeroCount,
				DistinctByteValues = distinct,
				MinimumByte = length == 0 ? (byte)0 : (byte)min,
				MaximumByte = length == 0 ? (byte)0 : (byte)max,
			};
		}
		finally
		{
			stream.Position = originalPosition;
		}
	}

	private static string ComputeSha256Range(Stream stream, long offset, long length)
	{
		if (offset < 0)
			throw new ArgumentOutOfRangeException(nameof(offset));

		if (length < 0)
			throw new ArgumentOutOfRangeException(nameof(length));

		if (offset > stream.Length || length > stream.Length - offset)
		{
			throw new InvalidDataException("Requested SHA-256 range exceeds stream bounds.");
		}

		long originalPosition = stream.Position;

		try
		{
			stream.Position = offset;

			using SHA256 sha = SHA256.Create();

			byte[] buffer = new byte[IoBufferSize];
			long remaining = length;

			while (remaining > 0)
			{
				int requested = (int)Math.Min(remaining, buffer.Length);

				int read = stream.Read(buffer, 0, requested);

				if (read <= 0)
				{
					throw new EndOfStreamException("Unexpected end of stream while hashing entry.");
				}

				sha.TransformBlock(buffer, 0, read, buffer, 0);

				remaining -= read;
			}

			sha.TransformFinalBlock(Array.Empty<byte>(), 0, 0);

			return ToHex(sha.Hash!);
		}
		finally
		{
			stream.Position = originalPosition;
		}
	}

	private static string ToHex(byte[] bytes)
	{
		return BitConverter.ToString(bytes).Replace("-", string.Empty);
	}

	// ============================================================
	// BUNDLE LIFETIME
	// ============================================================

	private sealed class LoadedBundle : IDisposable
	{
		public FileStream Stream { get; }
		public AssetsFileReader Reader { get; }
		public AssetBundleFile Bundle { get; }

		private bool _disposed;

		public LoadedBundle(FileStream stream, AssetsFileReader reader, AssetBundleFile bundle)
		{
			Stream = stream;
			Reader = reader;
			Bundle = bundle;
		}

		public void Dispose()
		{
			if (_disposed)
				return;

			_disposed = true;

			try
			{
				Bundle.Close();
			}
			catch
			{
				// Cleanup only.
			}

			try
			{
				Reader.Close();
			}
			catch
			{
				// Cleanup only.
			}

			try
			{
				Stream.Dispose();
			}
			catch
			{
				// Cleanup only.
			}
		}
	}

	private static LoadedBundle OpenBundle(string path)
	{
		FileStream? stream = null;
		AssetsFileReader? reader = null;
		AssetBundleFile? bundle = null;

		try
		{
			stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, IoBufferSize, FileOptions.SequentialScan);
			reader = new AssetsFileReader(stream);
			bundle = new AssetBundleFile();

			// NON chiudere reader dopo Read().
			// AssetBundleFile lo conserva internamente.
			bundle.Read(reader);

			return new LoadedBundle(stream, reader, bundle);
		}
		catch
		{
			try
			{
				bundle?.Close();
			}
			catch
			{
				// Cleanup only.
			}

			try
			{
				reader?.Close();
			}
			catch
			{
				// Cleanup only.
			}

			try
			{
				stream?.Dispose();
			}
			catch
			{
				// Cleanup only.
			}

			throw;
		}
	}

	// ============================================================
	// INFO
	// ============================================================

	private static void PrintBundleInfo(AssetBundleFile bundle, string prefix)
	{
		Log($"{prefix}Signature       : {bundle.Header.Signature}");
		Log($"{prefix}Unity           : {bundle.Header.EngineVersion}");
		Log($"{prefix}Version         : {bundle.Header.Version}");
		Log($"{prefix}Input mode      : {bundle.GetCompressionType()}");
		Log($"{prefix}Directory       : {bundle.BlockAndDirInfo.DirectoryInfos.Count} entries");
		Log($"{prefix}DataCompressed  : {bundle.DataIsCompressed}");
		Log($"{prefix}Blocks          : {bundle.BlockAndDirInfo.BlockInfos.Length}");
	}

	private static string TypeToString(byte compressionType)
	{
		return compressionType switch
		{
			0 => "None",
			1 => "LZMA",
			2 => "LZ4",
			3 => "LZ4HC/LZ4Fast",
			_ => $"Unknown({compressionType})"
		};
	}

	// ============================================================
	// TEMP FILES
	// ============================================================

	private static string CreateTempPath(string outputPath, string suffix)
	{
		string directory = Path.GetDirectoryName(outputPath) ?? Directory.GetCurrentDirectory();
		string filename = Path.GetFileName(outputPath);
		string random = Guid.NewGuid().ToString("N");

		return Path.Combine(directory, $"{filename}.{random}{suffix}");
	}

	private static void TryDeleteFile(string? path)
	{
		if (string.IsNullOrWhiteSpace(path))
			return;

		try
		{
			if (File.Exists(path))
			{
				File.Delete(path);
			}
		}
		catch
		{
			// Best-effort cleanup.
		}
	}

	// ============================================================
	// CLI
	// ============================================================

	private static bool HasFlag(string[] args, string flag)
	{
		foreach (string arg in args)
		{
			if (string.Equals(arg, flag, StringComparison.OrdinalIgnoreCase))
			{
				return true;
			}
		}

		return false;
	}

	private static string? GetOption(string[] args, params string[] names)
	{
		for (int i = 0; i < args.Length; i++)
		{
			foreach (string name in names)
			{
				if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase))
				{
					if (i + 1 >= args.Length)
						return null;

					return args[i + 1];
				}
			}
		}

		return null;
	}

	private static void PrintUsage()
	{
		Console.WriteLine("Unity Bundle Compressor");
		Console.WriteLine();
		Console.WriteLine("Usage:");
		Console.WriteLine("  UnityBundleCompressor.exe <input.bundle> <output.bundle>");
		Console.WriteLine("  UnityBundleCompressor.exe --input <input.bundle> --output <output.bundle> [--compression lzma|lz4]");
		Console.WriteLine();
		Console.WriteLine("Default compression: lzma");
		Console.WriteLine("LZ4 -> LZMA uses a safe intermediate uncompressed UnityFS step.");
		Console.WriteLine("Full validation is enabled by default.");
		Console.WriteLine("LZ4 output: implemented but disabled in this build.");
		Console.WriteLine();
		Console.WriteLine("Examples:");
		Console.WriteLine("  UnityBundleCompressor.exe game.bundle game_lzma.bundle");
		Console.WriteLine("  UnityBundleCompressor.exe --input game.bundle --output game_lzma.bundle --compression lzma");
		Console.WriteLine("  UnityBundleCompressor.exe --input game.bundle --output game_lz4.bundle --compression lz4");
	}

	// ============================================================
	// LOG
	// ============================================================

	private static void Log(string message = "")
	{
		lock (ConsoleLock)
		{
			string timestamp = DateTime.Now.ToString("HH:mm:ss.fff");
			Console.WriteLine($"[{timestamp}] {message}");
		}
	}

	// ============================================================
	// DATA CLASSES
	// ============================================================

	private sealed class BundleSnapshot
	{
		public string Label { get; set; } = string.Empty;
		public string Signature { get; set; } = string.Empty;
		public uint Version { get; set; }
		public string GenerationVersion { get; set; } = string.Empty;
		public string EngineVersion { get; set; } = string.Empty;
		public long DataAreaLength { get; set; }
		public string DataSha256 { get; set; } = string.Empty;
		public long ZeroByteCount { get; set; }
		public int DistinctByteValues { get; set; }
		public byte MinimumByte { get; set; }
		public byte MaximumByte { get; set; }
		public List<DirectorySnapshotEntry> Entries { get; } = new List<DirectorySnapshotEntry>();
	}

	private sealed class DirectorySnapshotEntry
	{
		public int Index { get; set; }
		public string Name { get; set; } = string.Empty;
		public long Offset { get; set; }
		public long Size { get; set; }
		public int Flags { get; set; }
		public string Sha256 { get; set; } = string.Empty;
	}

	private sealed class RangeProfile
	{
		public long Length { get; set; }
		public string Sha256 { get; set; } = string.Empty;
		public long ZeroByteCount { get; set; }
		public int DistinctByteValues { get; set; }
		public byte MinimumByte { get; set; }
		public byte MaximumByte { get; set; }
	}

	private sealed class BlockStats
	{
		public int BlockCount { get; set; }
		public long CompressedBytes { get; set; }
		public long DecompressedBytes { get; set; }
		public List<byte> CompressionTypes { get; set; } = new List<byte>();
	}

	private sealed class ByteComparisonResult
	{
		public bool AreEqual { get; set; }
		public long ComparedBytes { get; set; }
		public long FirstMismatchOffset { get; set; }
	}
}