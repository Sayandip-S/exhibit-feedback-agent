using UnityEngine;
using UnityEngine.UI;
using TMPro;
using System;
using System.Collections;
using System.Text;
using UnityEngine.Networking;

public class UIManager : MonoBehaviour
{
    [Header("Audio Recording")]
    public int sampleRate = 16000;
    public int maxRecordSeconds = 60;

    private AudioClip micClip;
    private string micDevice;
    private string currentSessionId;

    // Assign these in the Inspector (same as the old script)
    [Header("UI References")]
    public Button recordButton;
    public Button stopButton;

    public TMP_InputField transcriptField;
    public TMP_InputField botReplyField;

    public TextMeshProUGUI stateLabel;

    [Header("Backend")]
    [SerializeField] private string backendBaseUrl = "http://127.0.0.1:8000";

    [Header("Session Management")]
    [Tooltip("Reset session only when Idle and no interaction for this many seconds.")]
    public float idleResetSeconds = 30f;

    [Header("TTS Audio")]
    public AudioSource ttsAudioSource;
    
    private float lastInteractionTime;
    private enum AppState { Idle, Listening, Thinking, Speaking }
    private AppState currentState = AppState.Idle;
    private float _pipelineStartTime;

    void Start()
    {
        // Defensive checks
        if (recordButton == null || stopButton == null ||
            transcriptField == null || botReplyField == null || stateLabel == null)
        {
            Debug.LogError("UIManager: One or more UI references are not assigned in the Inspector.");
            return;
        }

        // Hook button events
        recordButton.onClick.AddListener(OnRecordClicked);
        stopButton.onClick.AddListener(OnStopClicked);

        currentSessionId = Guid.NewGuid().ToString();
        lastInteractionTime = Time.time;

        StartCoroutine(CallStartPrompt());

        if (Microphone.devices.Length > 0) micDevice = Microphone.devices[0];
        else Debug.LogWarning("No microphone detected.");

        UpdateUI();
        Debug.Log("UIManager started. session_id=" + currentSessionId);
    }

    void Update()
    {
        // Only reset when Idle (your requirement)
        if (currentState == AppState.Idle && (Time.time - lastInteractionTime) > idleResetSeconds)
        {
            ResetSession("idle timeout");
        }
    }

    void TouchInteraction()
    {
        // Call this whenever the user interacts or we receive valid results
        lastInteractionTime = Time.time;
    }

    void OnRecordClicked()
    {
        Debug.Log("Record button clicked");
        TouchInteraction();
        ChangeState(AppState.Listening);

        if (string.IsNullOrEmpty(micDevice))
        {
            Debug.LogError("No microphone available.");
            botReplyField.text = "(error) No microphone found.";
            ChangeState(AppState.Idle);
            return;
        }

        // Start recording
        micClip = Microphone.Start(micDevice, false, maxRecordSeconds, sampleRate);
    }

    // void OnRecordClicked()
    // {
    //     Debug.Log($"=== RECORD STARTING ===");
    //     Debug.Log($"maxRecordSeconds: {maxRecordSeconds}");
    //     Debug.Log($"Time: {Time.time}");
        
    //     // Check if we're already recording
    //     if (!string.IsNullOrEmpty(micDevice) && Microphone.IsRecording(micDevice))
    //     {
    //         Debug.LogError("Already recording when OnRecordClicked was called!");
    //         Microphone.End(micDevice);
    //     }
        
    //     TouchInteraction();
    //     ChangeState(AppState.Listening);

    //     if (string.IsNullOrEmpty(micDevice))
    //     {
    //         Debug.LogError("No microphone available.");
    //         botReplyField.text = "(error) No microphone found.";
    //         ChangeState(AppState.Idle);
    //         return;
    //     }

    //     // Start recording
    //     Debug.Log($"Calling Microphone.Start({micDevice}, false, {maxRecordSeconds}, {sampleRate})");
    //     micClip = Microphone.Start(micDevice, false, maxRecordSeconds, sampleRate);
        
    //     if (micClip == null)
    //     {
    //         Debug.LogError("Microphone.Start returned null!");
    //         ChangeState(AppState.Idle);
    //         return;
    //     }
        
    //     Debug.Log($"AudioClip created: length={micClip.length}s, samples={micClip.samples}, channels={micClip.channels}");
        
    //     // Check immediately if recording
    //     bool isRecording = Microphone.IsRecording(micDevice);
    //     int position = Microphone.GetPosition(micDevice);
    //     Debug.Log($"Immediate check - IsRecording: {isRecording}, Position: {position}");
        
    //     Debug.Log($"=== RECORD STARTED ===");
    // }

    void OnStopClicked()
    {
        _pipelineStartTime = Time.time;
        Debug.Log($"[TIMER] Started at {_pipelineStartTime:F2}s");

        Debug.Log("Stop button clicked");
        TouchInteraction();

        if (currentState == AppState.Listening && micClip != null)
        {
            Microphone.End(micDevice);
            StartCoroutine(SendAudioToSTTThenChat(micClip));
            return;
        }
        StopAllCoroutines();
        ChangeState(AppState.Idle);
    }

    void ChangeState(AppState newState)
    {
        currentState = newState;
        UpdateUI();
    }

    void UpdateUI()
    {
        stateLabel.text = "State: " + currentState;

        recordButton.interactable = (currentState == AppState.Idle);

        stopButton.interactable =
            (currentState == AppState.Listening ||
             currentState == AppState.Thinking ||
             currentState == AppState.Speaking);

        switch (currentState)
        {
            case AppState.Idle:      stateLabel.color = Color.blue;   break;
            case AppState.Listening: stateLabel.color = Color.green;  break;
            case AppState.Thinking:  stateLabel.color = Color.yellow; break;
            case AppState.Speaking:  stateLabel.color = Color.red;    break;
        }
    }

    // ---------- Session Management ----------
    public void ResetSession(string reason = "manual")
    {
        Debug.Log($"ResetSession triggered: {reason}");

        // new visitor = new session id
        currentSessionId = Guid.NewGuid().ToString();

        // clear UI
        transcriptField.text = "";
        botReplyField.text = "";

        // stop anything ongoing
        StopAllCoroutines();
        if (!string.IsNullOrEmpty(micDevice) && Microphone.IsRecording(micDevice))
        {
            Microphone.End(micDevice);
        }
        micClip = null;

        // reset timers/state
        lastInteractionTime = Time.time;
        ChangeState(AppState.Idle);
        StartCoroutine(CallStartPrompt());

        Debug.Log("New session_id=" + currentSessionId);
    }

    // ---------- Backend DTOs ----------
    [Serializable]
    private class ChatRequest
    {
        public string session_id;
        public string user_text;
        public object context;
    }

    [Serializable]
    private class ChatResponse
    {
        public string reply_text;
        public string emotion;
        public string[] keywords;
    }

    [Serializable]
    private class StartResponse
    {
        public string reply_text;
        public string emotion;
        public string[] keywords;
    }

    [Serializable]
    private class TTSRequest
    {
        public string text;
        public string voice;   // optional
        public string format;  // "wav"
    }


    IEnumerator CallChatBackend(string userText)
    {
        ChangeState(AppState.Thinking);

        var reqObj = new ChatRequest
        {
            session_id = currentSessionId,
            user_text = userText,
            context = null
        };

        string json = JsonUtility.ToJson(reqObj);
        byte[] bodyRaw = Encoding.UTF8.GetBytes(json);

        using (var request = new UnityWebRequest($"{backendBaseUrl}/chat", "POST"))
        {
            request.uploadHandler = new UploadHandlerRaw(bodyRaw);
            request.downloadHandler = new DownloadHandlerBuffer();
            request.SetRequestHeader("Content-Type", "application/json");

            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                string errBody = request.downloadHandler != null ? request.downloadHandler.text : "";
                Debug.LogError($"Chat request failed: {request.error}\nBody: {errBody}");
                botReplyField.text = $"(error) {request.error}";
                ChangeState(AppState.Idle);
                yield break;
            }

            string respJson = request.downloadHandler.text;
            ChatResponse resp = JsonUtility.FromJson<ChatResponse>(respJson);

            if (resp == null || string.IsNullOrEmpty(resp.reply_text))
            {
                Debug.LogError($"Failed to parse response JSON: {respJson}");
                botReplyField.text = "(error) Bad response JSON";
                ChangeState(AppState.Idle);
                yield break;
            }

            // successful chat = activity happened
            TouchInteraction();

            botReplyField.text = resp.reply_text;

            StartCoroutine(CallTTSAndPlay(resp.reply_text));
            yield break; // optional: stop the old 1 second fake speaking wait

            // ChangeState(AppState.Speaking);
            // yield return new WaitForSeconds(1.0f);
            // ChangeState(AppState.Idle);
        }
    }

    IEnumerator CallStartPrompt()
    {
        ChangeState(AppState.Thinking);

        string url = $"{backendBaseUrl}/start?session_id={currentSessionId}";
        using (var request = UnityWebRequest.Get(url))
        {
            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                Debug.LogError($"Start failed: {request.error}\nBody: {request.downloadHandler.text}");
                botReplyField.text = "(error) Could not start conversation.";
                ChangeState(AppState.Idle);
                yield break;
            }

            string respJson = request.downloadHandler.text;
            StartResponse resp = JsonUtility.FromJson<StartResponse>(respJson);

            if (resp == null || string.IsNullOrEmpty(resp.reply_text))
            {
                Debug.LogError($"Bad /start JSON: {respJson}");
                botReplyField.text = "(error) Bad start response.";
                ChangeState(AppState.Idle);
                yield break;
            }

            TouchInteraction(); // counts as activity

            botReplyField.text = resp.reply_text;

            ChangeState(AppState.Idle);
            yield break;

            // ChangeState(AppState.Speaking);
            // yield return new WaitForSeconds(1.0f);
            // ChangeState(AppState.Idle);
        }
    }

    IEnumerator SendAudioToSTTThenChat(AudioClip clip)
    {
        ChangeState(AppState.Thinking);

        byte[] wavData = WavUtility.FromAudioClip(clip, out string fileName);

        WWWForm form = new WWWForm();
        form.AddField("session_id", currentSessionId);
        form.AddField("language", "en"); // change to "de" if needed
        form.AddBinaryData("audio_file", wavData, fileName, "audio/wav");

        using (UnityWebRequest req = UnityWebRequest.Post($"{backendBaseUrl}/stt", form))
        {
            yield return req.SendWebRequest();

            if (req.result != UnityWebRequest.Result.Success)
            {
                Debug.LogError($"STT failed: {req.error}\nBody: {req.downloadHandler.text}");
                botReplyField.text = $"(stt error) {req.error}";
                ChangeState(AppState.Idle);
                yield break;
            }

            string json = req.downloadHandler.text;
            STTResponse stt = JsonUtility.FromJson<STTResponse>(json);

            if (stt == null || string.IsNullOrEmpty(stt.transcript))
            {
                Debug.LogError($"Bad STT JSON: {json}");
                botReplyField.text = "(stt error) bad response";
                ChangeState(AppState.Idle);
                yield break;
            }

            // successful stt = activity happened
            TouchInteraction();

            // Put transcript into UI
            transcriptField.text = stt.transcript;

            // Now call GPT chat with transcript
            yield return CallChatBackend(stt.transcript);

            float totalTime = Time.time - _pipelineStartTime;
            Debug.Log($"[TIMER] Total pipeline: {totalTime:F2}s ({totalTime*1000:F0}ms)");
            
        }
    }

    IEnumerator CallTTSAndPlay(string text)
    {
        if (ttsAudioSource == null)
        {
            Debug.LogWarning("TTS AudioSource not assigned. Skipping playback.");
            yield break;
        }

        // Keep speaking state while audio plays
        ChangeState(AppState.Speaking);

        var reqObj = new TTSRequest
        {
            text = text,
            voice = null,
            format = "mp3"
        };

        string json = JsonUtility.ToJson(reqObj);
        byte[] bodyRaw = Encoding.UTF8.GetBytes(json);

        using (var req = new UnityWebRequest($"{backendBaseUrl}/tts", "POST"))
        {
            req.uploadHandler = new UploadHandlerRaw(bodyRaw);
            req.downloadHandler = new DownloadHandlerAudioClip($"{backendBaseUrl}/tts", AudioType.MPEG)
            {
                streamAudio = true
            };
            req.SetRequestHeader("Content-Type", "application/json");

            float t0 = Time.realtimeSinceStartup;
            yield return req.SendWebRequest();

            if (req.result != UnityWebRequest.Result.Success)
            {
                Debug.LogError("TTS failed: " + req.error);
                ChangeState(AppState.Idle);
                yield break;
            }

            var clip = DownloadHandlerAudioClip.GetContent(req);
            if (clip == null || clip.length <= 0.01f)
            {
                Debug.LogError("TTS AudioClip is null/empty.");
                ChangeState(AppState.Idle);
                yield break;
            }

            Debug.Log($"[TTS] req done in {(Time.realtimeSinceStartup - t0) * 1000f:F0} ms, clip len={clip.length:F2}s");

            // Play
            ttsAudioSource.Stop();
            ttsAudioSource.clip = clip;
            ttsAudioSource.Play();

            // Wait until playback actually starts (1–2 frames), then until it ends
            yield return null;

            // If you want to be extra safe, wait for isPlaying to become true (up to ~0.5s)
            float startWait = Time.realtimeSinceStartup;
            while (!ttsAudioSource.isPlaying && (Time.realtimeSinceStartup - startWait) < 0.5f)
                yield return null;

            // Now wait until the audio finishes
            while (ttsAudioSource.isPlaying)
                yield return null;
        }

        ChangeState(AppState.Idle);
    }




    [Serializable]
    private class STTResponse
    {
        public string transcript;
        public float confidence;
        public string language;
        public int processing_time_ms;
    }

    // Optional helper methods
    public void UpdateTranscript(string text) => transcriptField.text = text;
    public void UpdateBotReply(string text) => botReplyField.text = text;
}
