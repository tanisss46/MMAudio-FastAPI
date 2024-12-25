from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
import subprocess
import os
import sys
import uuid
import logging

app = FastAPI()

# Logging setup
logging.basicConfig(level=logging.INFO)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://2474875b-0133-4a74-855e-a9f7a9bd6e24.lovableproject.com",  # Lovable domain
        "http://localhost",  # Local development
        "http://127.0.0.1"   # Localhost with IP
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase bağlantı bilgileri
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "processed_videos")

# Supabase istemcisi
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Geçici klasörler
TEMP_FOLDER = "./temp_files/"
OUTPUT_FOLDER = "./MMAudioDir/output/"
os.makedirs(TEMP_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


@app.post("/generate_sfx")
async def generate_sfx(
    prompt: str = Form(...),
    duration: int = Form(8),
    video: UploadFile = File(...)
):
    try:
        # 1. Videoyu geçici olarak kaydet
        video_filename = f"{uuid.uuid4()}_{video.filename}"
        video_path = os.path.join(TEMP_FOLDER, video_filename)
        with open(video_path, "wb") as f:
            f.write(await video.read())
        logging.info(f"Video uploaded to: {video_path}")

        # 2. MMAudio ile ses efekti oluştur
        audio_output_filename = f"{uuid.uuid4()}_audio.flac"
        audio_output_path = os.path.join(OUTPUT_FOLDER, audio_output_filename)
        cmd = [
            sys.executable,
            "./MMAudioDir/demo.py",
            f"--duration={duration}",
            f"--prompt={prompt}",
            f"--video={video_path}"
        ]
        process = subprocess.run(cmd, capture_output=True, text=True)
        if process.returncode != 0:
            logging.error(f"MMAudio error: {process.stderr}")
            raise HTTPException(
                status_code=500,
                detail=f"MMAudio error: {process.stderr}"
            )

        logging.info(f"Audio generated at: {audio_output_path}")

        # 3. FFmpeg ile videoya sesi ekle
        output_video_filename = f"{uuid.uuid4()}_output_video.mp4"
        output_video_path = os.path.join(OUTPUT_FOLDER, output_video_filename)
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", video_path,
            "-i", audio_output_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-strict", "experimental",
            output_video_path
        ]
        ffmpeg_process = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if ffmpeg_process.returncode != 0:
            logging.error(f"FFmpeg error: {ffmpeg_process.stderr}")
            raise HTTPException(
                status_code=500,
                detail=f"FFmpeg error: {ffmpeg_process.stderr}"
            )

        logging.info(f"Final video created at: {output_video_path}")

        # 4. Supabase'e yükle
        supabase_video_filename = f"processed_videos/{output_video_filename}"
        with open(output_video_path, "rb") as file_data:
            upload_response = supabase.storage.from_(SUPABASE_BUCKET).upload(
                supabase_video_filename, file_data, options={"content-type": "video/mp4"}
            )
        if upload_response.get("error"):
            logging.error("Error uploading video to Supabase")
            raise HTTPException(status_code=500, detail="Video upload failed")

        # 5. Public URL döndür
        public_video_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(supabase_video_filename)
        logging.info(f"Video available at: {public_video_url}")

        # Geçici dosyaları temizle
        os.remove(video_path)
        os.remove(audio_output_path)
        os.remove(output_video_path)

        return JSONResponse(
            {"status": "done", "video_url": public_video_url},
            status_code=200
        )
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
