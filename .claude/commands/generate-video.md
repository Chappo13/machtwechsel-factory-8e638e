# Generate Video

Run the full video generation pipeline for a topic.

Usage: /project:generate-video <topic> <lang>

Steps:
1. Generate script from topic
2. Improve script (3 iterations)
3. Apply virality filter
4. Generate TTS voiceover
5. Plan scenes and download stock clips
6. Find background music
7. Assemble video with FFmpeg
8. Generate YouTube metadata
