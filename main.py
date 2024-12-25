from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from supabase import create_client, Client
import subprocess
import os
import sys
import tempfile
import uuid

app = FastAPI()

# ... (CORS middleware ve Supabase istemci tanımları) ...

@app.post("/generate_sfx")
async def generate_sfx(
    prompt: str = Form(...),
    duration: int = Form(8),
    video: UploadFile = File(...)
):
    database_record_id = None
    supabase_video_url = None
    supabase_audio_url = None
    try:
        # 1. Supabase Kaydı Oluştur
        video_db_data = {"prompt": prompt, "duration": duration, "status": "processing"}
        response = supabase.table("user_generations").insert(video_db_data).execute()
        if response.error:
            raise HTTPException(status_code=500, detail=f"Veritabanı kaydı oluşturulamadı: {response.error.message}")
        database_record_id = response.data[0]['id']

        # 2. Videoyu Supabase'e Yükle
        video_filename = f"uploaded_videos/{database_record_id}_{video.filename}"
        contents = await video.read()
        response = supabase.storage.from_(os.environ.get("SUPABASE_BUCKET")).upload(
            video_filename, contents, options={"content-type": video.content_type}
        )
        if response.error:
            raise HTTPException(status_code=500, detail=f"Video Supabase'e yüklenemedi: {response.error.message}")
        supabase_video_url = supabase.storage.from_(os.environ.get("SUPABASE_BUCKET")).get_public_url(video_filename)

        # 3. Veritabanı Kaydını Video URL ile Güncelle
        response = supabase.table("user_generations").update({"video_url": supabase_video_url}).eq("id", database_record_id).execute()
        if response.error:
            raise HTTPException(status_code=500, detail=f"Veritabanı kaydı güncellenemedi: {response.error.message}")

        # 4. Ses Efekti Üret
        cmd = [
            sys.executable,
            "./MMAudioDir/demo.py",
            f"--duration={duration}",
            f"--prompt={prompt}",
            f"--video={supabase_video_url}"  # Orijinal video URL'si iletilebilir
        ]
        process = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("MMAudio script output:", process.stdout)
        if process.stderr:
            print("MMAudio script errors:", process.stderr)

        # 5. Ses Efektini Supabase'e Yükle
        audio_filename = f"generated_audio/{database_record_id}_audio.flac"
        output_audio_path = "./MMAudioDir/output/audio.flac"  # demo.py çıktı yolu
        if os.path.exists(output_audio_path):
            with open(output_audio_path, "rb") as file:
                response = supabase.storage.from_(os.environ.get("SUPABASE_BUCKET")).upload(
                    audio_filename, file, options={"content-type": "audio/flac"}
                )
            if response.error:
                raise HTTPException(status_code=500, detail=f"Ses efekti Supabase'e yüklenemedi: {response.error.message}")
            supabase_audio_url = supabase.storage.from_(os.environ.get("SUPABASE_BUCKET")).get_public_url(audio_filename)
        else:
            raise HTTPException(status_code=500, detail="Ses efekti dosyası bulunamadı.")

        # 6. Veritabanı Kaydını Ses URL ile Güncelle ve Tamamla
        response = supabase.table("user_generations").update({
            "audio_url": supabase_audio_url,
            "status": "completed"
        }).eq("id", database_record_id).execute()
        if response.error:
            raise HTTPException(status_code=500, detail=f"Veritabanı kaydı güncellenemedi: {response.error.message}")

        return JSONResponse({"id": database_record_id, "video_url": supabase_video_url, "audio_url": supabase_audio_url}, status_code=200)

    except subprocess.CalledProcessError as e:
        # ... (Hata yönetimi ve veritabanı güncelleme) ...
    except HTTPException as e:
        # ... (Hata yönetimi ve veritabanı güncelleme) ...
    except Exception as e:
        # ... (Hata yönetimi ve veritabanı güncelleme) ...
