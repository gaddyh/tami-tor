import os
import tempfile
import requests
from typing import Optional
from dotenv import load_dotenv
from adapters.primitivies import MediaInfo
from observability.obs import instrument_io
from google.oauth2 import service_account

load_dotenv(".venv/.env")

FB_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")

import ffmpeg
from google.cloud import speech_v1p1beta1 as speech

@instrument_io(
    name="transcribe_opus_file",
    meta={"agent": "tami", "operation": "transcribe_opus_file", "tool": "transcribe_opus_file", "schema": "input_path"},
    input_fn=lambda input_path: {
        "input_path": input_path
    },
    output_fn=lambda result: result,
    redact=True,
)
def transcribe_opus_file(input_path: str) -> str:
    # Create a temporary .wav file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_file:
        wav_path = wav_file.name

    # Convert .opus/.mp3/.ogg to .wav
    ffmpeg.input(input_path).output(
        wav_path, ac=1, ar=16000, format='wav', acodec='pcm_s16le'
    ).run(overwrite_output=True)

    try:
        with open(wav_path, "rb") as audio_file:
            content = audio_file.read()

        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            language_code="he-IL",
        )
        
        speech_creds = service_account.Credentials.from_service_account_file(
            "/etc/secrets/tami-463501-a8053925ce03.json"
        )
        client = speech.SpeechClient(credentials=speech_creds)
        response = client.recognize(config=config, audio=audio)
        return " ".join(
            result.alternatives[0].transcript for result in response.results
        )
    finally:
        os.remove(wav_path)

def get_facebook_media_url(media_id: str, access_token: str) -> str:
    url = f"https://graph.facebook.com/v16.0/{media_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()["url"]

def download_media_to_tempfile(media_url: str, access_token: str, mime_type: str) -> str:
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(media_url, headers=headers, stream=True)
    response.raise_for_status()

    # Normalize mime type
    mime_type = mime_type.split(";")[0].strip().lower()

    suffix = {
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/ogg": ".ogg",
        "audio/webm": ".webm"
    }.get(mime_type, ".mp3")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
        for chunk in response.iter_content(chunk_size=8192):
            tmp_file.write(chunk)
        return tmp_file.name

@instrument_io(
    name="transcribe_facebook_audio",
    meta={"agent": "tami", "operation": "transcribe_facebook_audio", "tool": "transcribe_facebook_audio", "schema": "MediaInfo.v1"},
    input_fn=lambda media_info: {
        "media_info": (media_info.model_dump() if hasattr(media_info, "model_dump")
                  else media_info.dict() if hasattr(media_info, "dict")
                  else media_info)
    },
    output_fn=lambda result: result,
    redact=True,
)
def transcribe_facebook_audio(media_info: MediaInfo) -> str:
    if not media_info.media_id:
        raise ValueError("MediaInfo must have a media_id")

    media_url = get_facebook_media_url(media_info.media_id, FB_TOKEN)
    file_path = download_media_to_tempfile(media_url, FB_TOKEN, media_info.mime_type)
    try:
        return transcribe_opus_file(file_path)
    finally:
        os.remove(file_path)


if __name__ == "__main__":

    media = MediaInfo(
        media_id="1052689170159365",
        mime_type="audio/ogg; codecs=opus",
        url=""
    )

    result = transcribe_facebook_audio(media)
    print("Transcription:", result)
