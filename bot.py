import asyncio
import logging
import os
import io
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile
import aiohttp
from aiohttp import web

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HF_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

# Kita beralih ke DeepAI API karena Hugging Face mematikan jalur gratisnya
DEEPAI_API_KEY = os.getenv("DEEPAI_API_KEY")
DEEPAI_URL = "https://api.deepai.org/api/torch-srgan"

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

import socket
import requests

def _upscale_sync(image_bytes: bytes) -> bytes:
    """Synchronous function using DeepAI to bypass all HF issues"""
    response = requests.post(
        DEEPAI_URL,
        headers={'api-key': DEEPAI_API_KEY},
        files={'image': image_bytes}
    )
    
    if response.status_code == 200:
        output_url = response.json().get('output_url')
        if not output_url:
            raise Exception("DeepAI tidak mengembalikan URL gambar hasil.")
        # Download gambar hasil dari URL tersebut
        img_response = requests.get(output_url)
        return img_response.content
    elif response.status_code == 401:
        raise Exception("API Key DeepAI tidak valid atau belum diisi.")
    elif response.status_code == 429:
        raise Exception("Server AI sedang sibuk. Mohon tunggu beberapa saat.")
    else:
        raise Exception(f"Error API (Code: {response.status_code}): {response.text}")

async def upscale_image(image_bytes: bytes) -> bytes:
    """Send image to DeepAI API for upscaling"""
    return await asyncio.to_thread(_upscale_sync, image_bytes)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Halo! 👋\n"
        "Saya adalah Bot Image Upscaler AI.\n"
        "Kirimkan foto (gambar biasa atau as document) kepada saya, "
        "dan saya akan meningkatkan kualitas/resolusinya!\n\n"
        "Catatan: Proses pertama mungkin agak lambat karena AI sedang 'bangun' (Cold Start)."
    )

@dp.message(lambda message: message.photo or message.document)
async def handle_image(message: types.Message):
    try:
        # Tentukan file id (dari photo compress atau document)
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.document and message.document.mime_type.startswith('image/'):
            file_id = message.document.file_id
        else:
            await message.reply("Mohon kirimkan file berupa gambar yang valid (JPG/PNG).")
            return

        status_msg = await message.reply("⏳ 1/3: Mengunduh gambar dari Telegram...")

        # Download file dari telegram
        file = await bot.get_file(file_id)
        file_path = file.file_path
        
        file_io = io.BytesIO()
        await bot.download_file(file_path, destination=file_io)
        image_bytes = file_io.getvalue()

        # Update status
        await status_msg.edit_text("⏳ 2/3: Memproses gambar dengan AI (Hugging Face)...\n*Ini mungkin memakan waktu hingga 30 detik.*")

        # Proses upscaling
        try:
            upscaled_bytes = await upscale_image(image_bytes)
        except Exception as e:
            await status_msg.edit_text(f"❌ Terjadi kesalahan:\n{str(e)}")
            return

        # Kirim balik ke user sebagai Document agar tidak dikompres lagi
        await status_msg.edit_text("✅ 3/3: Upscaling selesai! Mengirimkan hasil gambar...")
        result_file = BufferedInputFile(upscaled_bytes, filename="upscaled_result.png")
        
        # Kirim dokumen balasan (bisa butuh waktu jika file besar)
        await message.reply_document(document=result_file, caption="✨ Ini hasil gambar Anda yang sudah di-enhance!")
        
        # Hapus pesan status yang berderet-deret
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=status_msg.message_id)
        except:
            pass

    except Exception as e:
        await message.reply(f"❌ Gagal memproses gambar: {str(e)}")

# --- DUMMY WEB SERVER UNTUK UPTIMEROBOT (RENDER TRICK) ---
async def handle_ping(request):
    return web.Response(text="Bot is Alive and Awake!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Ambil port dari environment variable (Render akan menyediakan variable 'PORT', default 8080 untuk lokal)
    port = int(os.environ.get('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Web server started on port {port} for UptimeRobot pings.")

# --- MAIN RUNNER ---
async def main():
    # 1. Jalankan web server di background
    asyncio.create_task(start_web_server())
    
    # 2. Mulai bot Telegram (Hapus webhook lama jika ada, lalu polling)
    logging.info("Memulai bot Telegram...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
