#!/usr/bin/env python3
"""
Meshy.ai 3D Model Downloader
Скачивает 3D модели с Meshy.ai в формате GLB через Playwright.
Перехватывает расшифрованный glTF/GLB файл непосредственно из Web Worker в браузере.
"""

import os
import sys
import base64
from pathlib import Path
from playwright.sync_api import sync_playwright

# Включение UTF-8 для вывода в консоли Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


def extract_model_name(url: str) -> str:
    """Извлекает читаемое имя модели из URL."""
    clean_url = url.split("?")[0].rstrip("/")
    slug = clean_url.split("/")[-1]
    # Убираем UUID суффикс, если присутствует
    parts = slug.split("-019")
    return parts[0] if parts[0] else slug


def download_model(page_url: str, output_dir: str = '.') -> bool:
    """
    Загружает страницу Meshy.ai и сохраняет 3D модель (.glb).
    
    Args:
        page_url: Ссылка на страницу модели Meshy.ai
        output_dir: Директория для сохранения файла
    """
    print(f"[*] Загрузка модели по ссылке: {page_url}")
    
    model_name = extract_model_name(page_url)
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    output_file = output_dir_path / f"{model_name}.glb"

    # JS-скрипт внедрения перехватчика Web Worker
    worker_hook = """
        const origWorker = window.Worker;
        window.__DECRYPTED_GLB_B64__ = null;
        window.Worker = function(scriptUrl, options) {
            const w = new origWorker(scriptUrl, options);
            w.addEventListener('message', function(e) {
                if (e.data && e.data.type === 'process' && e.data.success && e.data.data) {
                    const bytes = new Uint8Array(e.data.data);
                    let binary = '';
                    const len = bytes.byteLength;
                    const chunkSize = 0x8000;
                    for (let i = 0; i < len; i += chunkSize) {
                        binary += String.fromCharCode.apply(null, bytes.subarray(i, Math.min(i + chunkSize, len)));
                    }
                    window.__DECRYPTED_GLB_B64__ = btoa(binary);
                }
            });
            return w;
        };
    """

    try:
        with sync_playwright() as p:
            print("[*] Запуск браузера...")
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.add_init_script(worker_hook)

            print("[*] Открытие страницы Meshy...")
            page.goto(page_url, wait_until="networkidle", timeout=60000)

            print("[*] Ожидание расшифровки и формирования 3D модели...")
            captured_b64 = None
            # Ожидаем перехват данных модели (до 30 секунд)
            for _ in range(30):
                try:
                    captured_b64 = page.evaluate("() => window.__DECRYPTED_GLB_B64__")
                    if captured_b64:
                        break
                except Exception:
                    pass
                page.wait_for_timeout(1000)

            browser.close()

            if not captured_b64:
                print("[-] Не удалось перехватить модель. Возможно, страница изменилась или модель недоступна.")
                return False

            raw_data = base64.b64decode(captured_b64)
            if not raw_data.startswith(b"glTF"):
                print("[-] Предупреждение: полученный файл не имеет заголовка glTF.")

            with open(output_file, "wb") as f:
                f.write(raw_data)

            size_mb = len(raw_data) / (1024 * 1024)
            print(f"[+] Модель успешно сохранена: {output_file.resolve()}")
            print(f"[+] Размер: {size_mb:.2f} MB")
            return True

    except Exception as e:
        print(f"[-] Произошла ошибка: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Использование:")
        print(f"  python {sys.argv[0]} <URL модели на Meshy.ai> [папка для сохранения]")
        print("\nПример:")
        print(f"  python {sys.argv[0]} https://www.meshy.ai/3d-models/Determined-Gaze-v2-019ab213-8acc-7826-b79b-b011a81e9180")
        sys.exit(1)

    url = sys.argv[1]
    if 'meshy.ai/3d-models/' not in url:
        print("[-] Ошибка: некорректный URL. Ожидается ссылка на модель с Meshy.ai")
        sys.exit(1)

    output_dir = sys.argv[2] if len(sys.argv) > 2 else '.'
    success = download_model(url, output_dir)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()