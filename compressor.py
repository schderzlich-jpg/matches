import os
import shutil
from PIL import Image

def compress_and_rename_images(directory="."):
    """
    Finds 'mac-*.png' images, compresses them locally using PIL,
    and saves them to a 'compressed' directory with the new naming convention.
    """
    
    # 1. Create 'compressed' folder
    compressed_dir = os.path.join(directory, "compressed")
    if not os.path.exists(compressed_dir):
        os.makedirs(compressed_dir)
        print(f"Created directory: {compressed_dir}")

    # 2. Find PNG files starting with 'mac-'
    files = [f for f in os.listdir(directory) if f.startswith("mac-") and f.endswith(".png")]
    
    if not files:
        print("No 'mac-*.png' files found to compress.")
        return

    print(f"Found {len(files)} files to compress...")

    for filename in files:
        filepath = os.path.join(directory, filename)
        
        # Determine new filename: 'mac-1.png' -> 'compressed-mac-1.png'
        # The user requested format: "compressed-mac-1" (presumably with .png extension)
        # Determine new filename: 'mac-1.png'
        # Kullanıcının isteği: "Başına compressed yazma"
        new_filename = filename
        new_filepath = os.path.join(compressed_dir, new_filename)

        try:
            # 3. Compress using Pillow
            # 'optimize=True' and 'quality=85' usually gives good compression with little visual loss
            with Image.open(filepath) as img:
                # Kullanıcının "%10 kadar compress" isteği:
                # PNG için 'save(quality=...)' parametresi yoktur. 
                # Dosya boyutunu ciddi oranda düşürmek için 'Quantization' (renk azaltma) kullanılır.
                # Online araçlar genellikle 8-bit (256 renk) PNG'ye dönüştürür.
                # Bu işlem kalite kaybını en aza indirerek boyutu %60-80 oranında düşürebilir.
                
                # Kullanıcı isteği: "Max %10 compress" (Görüntü bozulmasın)
                # Quantization (renk azaltma) kaldırıldı, sadece lossless optimize yapıyoruz.
                # compress_level varsayılan (6) veya hafif artırılabilir, ama optimize=True yeterlidir.
                img.save(new_filepath, "PNG", optimize=True)
                
            print(f"✅ Compressed & Saved: {new_filename}")
            
        except Exception as e:
            print(f"❌ Failed to compress {filename}: {e}")

if __name__ == "__main__":
    compress_and_rename_images(os.getcwd())
