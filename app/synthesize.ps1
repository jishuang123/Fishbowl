# Static helper only. Reply text arrives as UTF-8 JSON on stdin, never as code.
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$fishSynth = $null
$fishStream = $null
try {
    Add-Type -AssemblyName System.Speech
    $fishInput = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $fishText = [string]$fishInput.text
    if ([string]::IsNullOrWhiteSpace($fishText) -or $fishText.Length -gt 3000) { throw 'Invalid text' }
    $fishSynth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
    $fishVoices = @($fishSynth.GetInstalledVoices() | Where-Object {
        $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'zh-*'
    })
    if ($fishVoices.Count -eq 0) { throw 'No Chinese voice' }
    $fishVoice = $fishVoices | Sort-Object @{Expression={
        if ($_.VoiceInfo.Name -eq 'Microsoft Yaoyao') { 0 }
        elseif ($_.VoiceInfo.Culture.Name -eq 'zh-CN' -and $_.VoiceInfo.Gender -eq 'Female') { 1 }
        else { 2 }
    }} | Select-Object -First 1
    $fishSynth.SelectVoice($fishVoice.VoiceInfo.Name)
    $fishSynth.Rate = 0
    $fishStream = [System.IO.MemoryStream]::new()
    $fishFormat = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(24000,
        [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
        [System.Speech.AudioFormat.AudioChannel]::Mono)
    $fishSynth.SetOutputToAudioStream($fishStream, $fishFormat)
    $fishSynth.Speak($fishText)
    $fishSynth.SetOutputToNull()
    $fishResult = @{pcm=[Convert]::ToBase64String($fishStream.ToArray()); voice=$fishVoice.VoiceInfo.Name}
    [Console]::Out.Write(($fishResult | ConvertTo-Json -Compress))
} catch {
    [Console]::Out.Write('{"error":"Local speech synthesis unavailable"}')
    exit 1
} finally {
    if ($null -ne $fishSynth) { $fishSynth.Dispose() }
    if ($null -ne $fishStream) { $fishStream.Dispose() }
}
