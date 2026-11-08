# AI-generated images

Put images in this folder that you know were generated or heavily manipulated
by a model. 20+ files is a good start.

What helps:
- several generators (Midjourney, Stable Diffusion/Flux, DALL·E, Firefly,
  Ideogram, phone "AI" features)
- the same images after being compressed or screenshotted, because that strips
  the metadata and sensor cues the detector relies on
- a mix of photorealistic and stylised output

What hurts:
- only one generator at one resolution (the detector will overfit that look)
- duplicates

Run the calibration with:

    cd backend
    .venv\Scripts\python.exe tools\calibrate.py

Do not tune on the same images you test on. If you need an honest number, hold
a few files back and run the pipeline on those afterwards.
