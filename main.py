from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from supabase import create_client, Client
import subprocess
import os
import sys
import tempfile
import uuid  # For generating unique filenames
from fastapi.middleware.cors import CORSMiddleware  # Import the middleware

print(sys.path)
print(sys.executable)

app = FastAPI()

# Add CORS middleware here, before any routes are defined
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://lovable.dev/projects/2474875b-0133-4a74-855e-a9f7a9bd6e24"],  # Use the provided Lovable URL
    allow_credentials=True,
    allow_methods=["POST"],  # Be specific about allowed methods
    allow_headers=["*"],  # Allow all headers for simplicity, consider narrowing down in production
)

# Initialize Supabase client (replace with your actual URL and Key)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase URL and Key environment variables must be set.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Replace with your Supabase storage bucket name
SUPABASE_BUCKET = "your-storage-bucket-name"

@app.post("/generate_sfx")
async def generate_sfx(
    prompt: str = Form(...),
    duration: int = Form(8),
    video: UploadFile = File(None)
):
    supabase_video_url = None
    supabase_audio_url = None
    database_record_id = None

    try:
        # 1. Upload Video to Supabase (if provided)
        if video:
            video_filename = f"{uuid.uuid4()}_{video.filename}"
            try:
                response = supabase.storage.from_(SUPABASE_BUCKET).upload(
                    f"uploaded_videos/{video_filename}", video.file
                )
                if response.status_code == 200:
                    supabase_video_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(f"uploaded_videos/{video_filename}")
                else:
                    raise HTTPException(status_code=500, detail=f"Error uploading video to Supabase: {response.text}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error uploading video to Supabase: {e}")

        # 2. Create Metadata Record in Supabase
        try:
            video_db_data = {"prompt": prompt, "duration": duration, "video_url": supabase_video_url, "status": "processing"}
            response = supabase.table("user_generations").insert(video_db_data).execute()
            if response.error:
                raise HTTPException(status_code=500, detail=f"Error creating database record: {response.error.message}")
            database_record_id = response.data[0]['id']
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error creating database record: {e}")

        # 3. Execute MMAudio demo.py
        cmd = [
            sys.executable,
            "./MMAudioDir/demo.py",
            f"--duration={duration}",
            f"--prompt={prompt}"
        ]
        if supabase_video_url:
            cmd.append(f"--video={supabase_video_url}")

        process = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("MMAudio script output:", process.stdout)
        if process.stderr:
            print("MMAudio script errors:", process.stderr)

        # 4. Upload Generated Audio to Supabase
        output_audio_path = "./MMAudioDir/output/audio.flac"  # Assuming default output path
        if os.path.exists(output_audio_path):
            audio_filename = f"{uuid.uuid4()}_audio.flac"
            try:
                with open(output_audio_path, "rb") as audio_file:
                    response = supabase.storage.from_(SUPABASE_BUCKET).upload(
                        f"generated_audio/{audio_filename}", audio_file
                    )
                if response.status_code == 200:
                    supabase_audio_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(f"generated_audio/{audio_filename}")
                else:
                    raise HTTPException(status_code=500, detail=f"Error uploading audio to Supabase: {response.text}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error uploading audio to Supabase: {e}")
        else:
            raise HTTPException(status_code=500, detail="Generated audio file not found.")

        # 5. Update Metadata Record with Audio URL
        try:
            response = supabase.table("user_generations").update({"audio_url": supabase_audio_url, "status": "completed"}).eq("id", database_record_id).execute()
            if response.error:
                raise HTTPException(status_code=500, detail=f"Error updating database record with audio URL: {response.error.message}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error updating database record with audio URL: {e}")

        return {"status": "done", "audio_url": supabase_audio_url, "video_url": supabase_video_url, "database_id": database_record_id}

    except HTTPException as e:
        # Update database record with failure status
        if database_record_id:
            try:
                supabase.table("user_generations").update({"status": "failed", "error_message": str(e.detail)}).eq("id", database_record_id).execute()
            except Exception as db_update_error:
                print(f"Error updating database with failure status: {db_update_error}")
        raise e
    except subprocess.CalledProcessError as e:
        # Update database record with failure status
        if database_record_id:
            try:
                supabase.table("user_generations").update({"status": "failed", "error_message": f"MMAudio script failed: {e.stderr}"}).eq("id", database_record_id).execute()
            except Exception as db_update_error:
                print(f"Error updating database with subprocess failure status: {db_update_error}")
        raise HTTPException(status_code=500, detail=f"MMAudio script failed: {e.stderr}")
    except Exception as e:
        # Update database record with failure status
        if database_record_id:
            try:
                supabase.table("user_generations").update({"status": "failed", "error_message": str(e)}).eq("id", database_record_id).execute()
            except Exception as db_update_error:
                print(f"Error updating database with general failure status: {db_update_error}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up temporary files if needed (though demo.py seems to handle this)
        pass
