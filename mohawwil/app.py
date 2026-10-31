"""نقطة دخول بديلة: بعض الاستضافات (مثل FPS.ms) تشغّل app.py افتراضياً."""
import asyncio

from main import main

if __name__ == "__main__":
    asyncio.run(main())
