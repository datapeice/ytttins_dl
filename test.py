import yt_dlp
import sys

def progress_hook(d):
    """Хук для отображения прогресса"""
    if d['status'] == 'downloading':
        try:
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            
            if total > 0:
                percent = int((downloaded / total) * 100)
                bar_length = 30
                filled = int((bar_length * downloaded) / total)
                bar = '=' * filled + '>' + ' ' * (bar_length - filled - 1)
                
                speed = d.get('speed', 0)
                speed_str = f"{speed/1024/1024:.1f}MB/s" if speed else "0MB/s"
                
                downloaded_mb = downloaded / 1024 / 1024
                total_mb = total / 1024 / 1024
                
                sys.stdout.write(f'\r[{bar}] {percent}% {downloaded_mb:.1f}MB/{total_mb:.1f}MB @ {speed_str}')
                sys.stdout.flush()
        except:
            pass
    elif d['status'] == 'finished':
        print('\n✅ Скачивание завершено, обработка...')

def main():
    print("=" * 60)
    print("   YouTube Video Downloader (yt-dlp с обходом блокировки)")
    print("=" * 60)
    
    url = input("\nВведите ссылку на YouTube видео: ").strip()
    
    if not url:
        print("❌ Пустая ссылка!")
        return
    
    # Настройки yt-dlp с обходом блокировки
    ydl_opts = {
        'format': 'best',  # Лучшее качество (видео+аудио вместе)
        'outtmpl': '%(title)s.%(ext)s',
        'progress_hooks': [progress_hook],
        'quiet': False,
        'no_warnings': False,
        
        # КРИТИЧЕСКИ ВАЖНЫЕ настройки для обхода блокировки YouTube
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],  # Использовать Android клиент
                'player_skip': ['webpage', 'configs'],
            }
        },
        
        # Дополнительные настройки
        'nocheckcertificate': True,
        'geo_bypass': True,
        'age_limit': None,
        
        # User-Agent чтобы прикинуться браузером
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        }
    }
    
    try:
        print("\n🔍 Получение информации о видео...")
        
        # Сначала получаем информацию без скачивания
        with yt_dlp.YoutubeDL({'quiet': True, **ydl_opts}) as ydl:
            info = ydl.extract_info(url, download=False)
            
            print("\n" + "=" * 60)
            print(f"📝 Название: {info.get('title')}")
            print(f"👤 Автор: {info.get('uploader')}")
            print(f"⏱️  Длительность: {info.get('duration')} сек")
            print(f"👁️  Просмотров: {info.get('view_count', 0):,}")
            print("=" * 60)
            
            # Показываем доступные форматы
            formats = info.get('formats', [])
            
            print("\n📊 Доступные форматы:")
            print("  1. Лучшее качество (видео+аудио)")
            print("  2. 1080p (если доступно)")
            print("  3. 720p")
            print("  4. 480p")
            print("  5. Только аудио (лучшее качество)")
            
            choice = input("\nВыберите формат (1-5) или Enter для варианта 1: ").strip()
            
            # Настраиваем формат в зависимости от выбора
            if choice == '2':
                ydl_opts['format'] = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]'
            elif choice == '3':
                ydl_opts['format'] = 'bestvideo[height<=720]+bestaudio/best[height<=720]'
            elif choice == '4':
                ydl_opts['format'] = 'bestvideo[height<=480]+bestaudio/best[height<=480]'
            elif choice == '5':
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['outtmpl'] = '%(title)s.%(ext)s'
            else:
                ydl_opts['format'] = 'best'
        
        print("\n📥 Начинаю скачивание...\n")
        
        # Теперь скачиваем
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        print("\n✨ Готово! Файл сохранен в текущей директории.")
        
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        
        print(f"\n❌ Ошибка скачивания: {error_msg}")
        
        if 'Sign in to confirm you' in error_msg or 'age' in error_msg.lower():
            print("\n💡 Видео требует подтверждения возраста!")
            print("Решение:")
            print("  1. Экспортируйте cookies из браузера где вы залогинены")
            print("  2. Используйте: yt-dlp --cookies cookies.txt URL")
        elif 'Private video' in error_msg:
            print("\n💡 Это приватное видео - нужна авторизация")
        elif 'Video unavailable' in error_msg:
            print("\n💡 Видео недоступно в вашем регионе или удалено")
        else:
            print("\n💡 Попробуйте:")
            print("  1. Обновить yt-dlp: pip install -U yt-dlp")
            print("  2. Использовать другое видео")
            print("  3. Проверить подключение к интернету")
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()