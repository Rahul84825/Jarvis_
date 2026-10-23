param([string]$ImagePath)
$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    Add-Type -AssemblyName System.IO

    $asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { 
        $_.Name -eq 'AsTask' -and 
        $_.GetParameters().Count -eq 1 -and 
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' 
    }

    $fullPath = [System.IO.Path]::GetFullPath($ImagePath)

    [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
    [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
    [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null

    $fileOp = [Windows.Storage.StorageFile]::GetFileFromPathAsync($fullPath)
    $fileTask = $asTaskGeneric[0].MakeGenericMethod([Windows.Storage.StorageFile]).Invoke($null, @($fileOp))
    $file = $fileTask.GetAwaiter().GetResult()

    $streamOp = $file.OpenAsync([Windows.Storage.FileAccessMode]::Read)
    $streamTask = $asTaskGeneric[0].MakeGenericMethod([Windows.Storage.Streams.IRandomAccessStream]).Invoke($null, @($streamOp))
    $stream = $streamTask.GetAwaiter().GetResult()

    $decoderOp = [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)
    $decoderTask = $asTaskGeneric[0].MakeGenericMethod([Windows.Graphics.Imaging.BitmapDecoder]).Invoke($null, @($decoderOp))
    $decoder = $decoderTask.GetAwaiter().GetResult()

    $softwareBitmapOp = $decoder.GetSoftwareBitmapAsync()
    $softwareBitmapTask = $asTaskGeneric[0].MakeGenericMethod([Windows.Graphics.Imaging.SoftwareBitmap]).Invoke($null, @($softwareBitmapOp))
    $softwareBitmap = $softwareBitmapTask.GetAwaiter().GetResult()

    $ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $ocrEngine) {
        $ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US'))
    }
    if ($null -eq $ocrEngine) {
        Write-Output '{"error": "Windows.Media.Ocr engine unavailable for installed languages", "text_b64": "", "lines_b64": []}'
        exit 0
    }

    $ocrOp = $ocrEngine.RecognizeAsync($softwareBitmap)
    $ocrTask = $asTaskGeneric[0].MakeGenericMethod([Windows.Media.Ocr.OcrResult]).Invoke($null, @($ocrOp))
    $ocrResult = $ocrTask.GetAwaiter().GetResult()

    $rawText = if ($null -ne $ocrResult.Text) { $ocrResult.Text } else { "" }
    $textB64 = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($rawText))
    $linesB64 = @($ocrResult.Lines | ForEach-Object { [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($_.Text)) })

    $res = @{
        text_b64 = $textB64
        lines_b64 = $linesB64
        line_count = $linesB64.Count
    }
    $res | ConvertTo-Json -Compress
} catch {
    $errB64 = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($_.Exception.Message))
    Write-Output "{`"error_b64`": `"$errB64`", `"text_b64`": `"`", `"lines_b64`": []}"
}
