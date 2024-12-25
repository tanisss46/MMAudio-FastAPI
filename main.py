from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
import subprocess
import os
import sys
import uuid

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://2474875b-0133-4a74-855e-a9f7a9bd6e24.lovableproject.com"],  # Sadece bu domain izinli
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
            raise HTTPException(
                status_code=500,
                detail=f"Ses efekti oluşturma başarısız: {process.stderr}"
            )

        if not os.path.exists(audio_output_path):
            raise HTTPException(status_code=500, detail="Ses dosyası bulunamadı")

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
        subprocess.run(ffmpeg_cmd, check=True)

        if not os.path.exists(output_video_path):
            raise HTTPException(status_code=500, detail="Çıktı videosu oluşturulamadı")

        # 4. Çıktı videosunu Supabase'e yükle
        supabase_video_filename = f"processed_videos/{output_video_filename}"
        with open(output_video_path, "rb") as file_data:
            response = supabase.storage.from_(SUPABASE_BUCKET).upload(
                supabase_video_filename, file_data, options={"content-type": "video/mp4"}
            )
        if response.get("error"):
            raise HTTPException(status_code=500, detail="Çıktı videosu yüklenemedi")

        public_video_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(supabase_video_filename)

        # 5. Geçici dosyaları temizle
        os.remove(video_path)
        os.remove(audio_output_path)
        os.remove(output_video_path)

        return JSONResponse(
            {"status": "done", "video_url": public_video_url},
            status_code=200
        )

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bir hata oluştu: {str(e)}")
