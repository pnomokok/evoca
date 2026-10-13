"""Quick test: transcribe an English audio file with Amazon Transcribe.

Prints the transcript, word-level timestamps and how long the job took.
Usage: python experiments/transcribe_test.py experiments/audio/test1.m4a
"""

import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"


def ensure_bucket(s3, bucket: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        s3.create_bucket(Bucket=bucket)  # us-east-1 needs no LocationConstraint
        print("Created bucket:", bucket)


def main(audio_path: str) -> None:
    path = Path(audio_path)
    session = boto3.Session(region_name=REGION)
    account_id = session.client("sts").get_caller_identity()["Account"]

    bucket = f"evoca-audio-{account_id}"
    s3 = session.client("s3")
    ensure_bucket(s3, bucket)
    key = f"stt-test/{path.name}"
    s3.upload_file(str(path), bucket, key)
    print("Uploaded:", f"s3://{bucket}/{key}")

    transcribe = session.client("transcribe")
    job_name = f"evoca-test-{uuid.uuid4().hex[:8]}"
    started = time.time()
    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": f"s3://{bucket}/{key}"},
        LanguageCode="en-US",
    )

    while True:
        job = transcribe.get_transcription_job(TranscriptionJobName=job_name)["TranscriptionJob"]
        status = job["TranscriptionJobStatus"]
        if status in ("COMPLETED", "FAILED"):
            break
        time.sleep(3)
    elapsed = time.time() - started

    if status == "FAILED":
        print("Job failed:", job.get("FailureReason"))
        return

    with urllib.request.urlopen(job["Transcript"]["TranscriptFileUri"]) as response:
        data = json.load(response)

    print(f"\nJob took {elapsed:.1f} seconds")
    print("\nTranscript:")
    print(data["results"]["transcripts"][0]["transcript"])

    words = [item for item in data["results"]["items"] if item["type"] == "pronunciation"]
    print(f"\nWords with timestamps ({len(words)} total, first 15 shown):")
    for item in words[:15]:
        best = item["alternatives"][0]
        print(f"  {item['start_time']:>7}s - {item['end_time']:>7}s  {best['content']}  (confidence {best['confidence']})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python experiments/transcribe_test.py <audio file>")
    main(sys.argv[1])