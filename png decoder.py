import zlib
import struct
import numpy as np

def read_chunk(file):
    length = int.from_bytes(file.read(4), byteorder ='big')
    chunk_name = (file.read(4)).decode('utf-8')
    data = file.read(length)
    file.read(4) #crc
    return chunk_name, data

def write_chunk(out, chunk_type, data):
    assert len(chunk_type) == 4
    out.write(struct.pack(">L", len(data)))
    out.write(chunk_type)
    out.write(data)
    checksum = zlib.crc32(chunk_type)
    checksum = zlib.crc32(data, checksum)
    out.write(struct.pack(">L", checksum))

def open_image(path):

    with open(path, 'rb') as f:
    
        #######################
        # Check png signature
        #######################

        header = f.read(8)

        L = list(byte for byte in header)
        R = [137, 80, 78, 71, 13, 10, 26, 10]
        for i in range(8):
            if L[i] != R[i]:
                print("not a png file!")
                exit()

        #######################
        # Read IHDR
        #######################

        length = int.from_bytes(f.read(4), byteorder ='big')
        chunk_name = (f.read(4)).decode('utf-8')

        width = int.from_bytes(f.read(4), byteorder ='big')
        height = int.from_bytes(f.read(4), byteorder ='big')

        bit_depth = int.from_bytes(f.read(1), byteorder ='big')
        color_type = int.from_bytes(f.read(1), byteorder ='big') # 0 - greyscale, 2 - rgb, 3 - PLTE, 4 - greyscale + alpha, 6 - rgb + alpha
        compression_method = int.from_bytes(f.read(1), byteorder ='big')
        filter_method = int.from_bytes(f.read(1), byteorder ='big')
        interlace_method = int.from_bytes(f.read(1), byteorder ='big')

        crc = f.read(4)

        bdCorrect = False
        if color_type == 0:
            for n in [1, 2, 4, 8, 16]:
                if n == bit_depth:
                    bdCorrect = True
            if bdCorrect != True:
                raise Exception("Incorrect bit depth for this type of color type")
        elif color_type == 2:
            for n in [8, 16]:
                if n == bit_depth:
                    bdCorrect = True
            if bdCorrect != True:
                raise Exception("Incorrect bit depth for this type of color type")
        elif color_type == 3:
            raise Exception("Indexed color not supported!")
        elif color_type == 4:
            raise Exception("Greyscale with alpha not supported!")
        elif color_type == 6:
            raise Exception("RGBA not supported!")


        if bit_depth != 8:
            raise Exception(f"The only bit depth supported is 8, bit depth in image is {bit_depth}")

        #######################
        # Read IDAT
        #######################
        
        idat_data = []

        while(True):
            name, data = read_chunk(f)
            if name == 'IEND':
                break
            
            idat_data.append(data)

        pixel_data = b''.join(d for d in idat_data)
        pixel_data = zlib.decompress(pixel_data)

        def PaethPredictor(a, b, c):
            p = a + b - c
            pa = abs(p - a)
            pb = abs(p - b)
            pc = abs(p - c)
            if pa <= pb and pa <= pc:
                Pr = a
            elif pb <= pc:
                Pr = b
            else:
                Pr = c
            return Pr

        Recon = []
        if color_type == 0:
            bytesPerPixel = 1
        elif color_type == 2:
            bytesPerPixel = 3
        stride = width * bytesPerPixel

        def Recon_a(r, c):
            return Recon[r * stride + c - bytesPerPixel] if c >= bytesPerPixel else 0

        def Recon_b(r, c):
            return Recon[(r-1) * stride + c] if r > 0 else 0

        def Recon_c(r, c):
            return Recon[(r-1) * stride + c - bytesPerPixel] if r > 0 and c >= bytesPerPixel else 0


        i = 0
        for r in range(height):
            filter_type = pixel_data[i]
            i += 1
            for c in range(stride): 
                Filt_x = pixel_data[i]
                i += 1
                if filter_type == 0: # None
                    Recon_x = Filt_x
                elif filter_type == 1: # Sub
                    Recon_x = Filt_x + Recon_a(r, c)
                elif filter_type == 2: # Up
                    Recon_x = Filt_x + Recon_b(r, c)
                elif filter_type == 3: # Average
                    Recon_x = Filt_x + (Recon_a(r, c) + Recon_b(r, c)) // 2
                elif filter_type == 4: # Paeth
                    Recon_x = Filt_x + PaethPredictor(Recon_a(r, c), Recon_b(r, c), Recon_c(r, c))
                else:
                    raise Exception('unknown filter type: ' + str(filter_type))
                Recon.append(Recon_x & 0xff)

        image = np.array(Recon).reshape((height, width, 3))

        return image, width, height


def save_image(file_name, image, width, height):

    with open(file_name, 'wb') as f:

        # png signature
        signature = struct.pack('8B', 137, 80, 78, 71, 13, 10, 26, 10)
        f.write(signature)

        # IHDR chunk
        ihdr_name = (b'IHDR')
        ihdr_data = struct.pack("!2I5B", width, height, 8, 2, 0, 0, 0)
        write_chunk(f, ihdr_name, ihdr_data)

        # IDAT chunks
        lines = []
        for h in range(0,height):
            line = []
            line.append(0)
            for w in range(0, width):
                line.append(image[h][w][0])
                line.append(image[h][w][1])
                line.append(image[h][w][2])
            lines.append(line)

        raw_pixel_data = []
        for line in lines:
            for num in line:
                raw_pixel_data.append(num)

        byte_data = bytearray(raw_pixel_data)

        compressed = zlib.compress(byte_data)

        write_chunk(f, b"IDAT", compressed)

        # IEND chunk

        write_chunk(f, b"IEND", bytearray())

def rgb_to_grayscale(image, width, height):
    converted = np.zeros((height,width), dtype=int)
    
    for h in range(0,height):
        for w in range(0, width):
            converted[h][w] = image[h][w][0]

    return converted

def greyscale_to_rgb(image, width, height):
    converted = np.zeros((height,width, 3), dtype=int)

    for h in range(height):
        for w in range(width):
            converted[h][w][0] = image[h][w]
            converted[h][w][1] = image[h][w]
            converted[h][w][2] = image[h][w]

    return converted

