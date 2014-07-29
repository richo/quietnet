import sys
import time
import pyaudio
import quietnet
import options
import psk

FORMAT = pyaudio.paInt16
CHANNELS = options.channels
RATE = options.rate
FREQ = options.freq
FREQ_OFF = 0
FRAME_LENGTH = options.frame_length
DATASIZE = options.datasize

quiet = False

p = pyaudio.PyAudio()
stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True)

user_input = input if sys.version_info.major >= 3 else raw_input

def make_buffer_from_bit_pattern(pattern, on_freq, off_freq):
    """ Takes a pattern and returns an audio buffer that encodes that pattern """
    # the key's middle value is the bit's value and the left and right bits are the bits before and after
    # the buffers are enveloped to cleanly blend into each other

    last_bit = pattern[-1]
    output_buffer = []
    offset = 0

    for i in range(len(pattern)):
        bit = pattern[i]
        if i < len(pattern) - 1:
            next_bit = pattern[i+1]
        else:
            next_bit = pattern[0]

        freq = on_freq if bit == '1' else off_freq
        tone = quietnet.tone(freq, DATASIZE, offset=offset)
        output_buffer += quietnet.envelope(tone, left=last_bit=='0', right=next_bit=='0')
        offset += DATASIZE
        last_bit = bit

    return quietnet.pack_buffer(output_buffer)

def convert_message_to_bits(msg):
    for c in map(ord, msg):
        bits = []
        for i in range(8, 0, -1):
            i -= 1
            bits.append(1 if c & (1 << i) else 0)
            yield bits[-1]
        print repr(list(reversed(bits)))

def play_buffer(buffer):
    output = ''.join(buffer)
    stream.write(output)

def send_bytes(message):
    for idx, bit in enumerate(convert_message_to_bits(message)):
        # if idx != 0 and idx % 8 * 16 == 0:
        #     print("Waiting for a moment to allow sigils + resync")
        #     time.sleep(5)
        # if idx != 0 and idx % (8 * 8) == 0:
        #     print("Sent %d bytes" % (idx / 8))
        pattern = psk.encode([bit], options.sigil)
        buffer = make_buffer_from_bit_pattern(pattern, FREQ, FREQ_OFF)
        play_buffer(buffer)
        time.sleep(0.2)

if __name__ == "__main__":
    input_s = "> "
    if "-q" in sys.argv:
        sys.argv.pop(sys.argv.index("-q"))
        quiet = True
        input_s = ""
    if len(sys.argv) > 1:
        FREQ = int(sys.argv[1])

    if not quiet:
        print("Welcome to quietnet. Use ctrl-c to exit")

    try:
        # get user input and play message
        while True:
            message = user_input(input_s)
            try:
              bits = convert_message_to_bits(message)
              print(repr(bits))
              for bit in bits:
                  pattern = psk.encode([bit], options.sigil)
                  buffer = make_buffer_from_bit_pattern(pattern, FREQ, FREQ_OFF)
                  play_buffer(buffer)
                  time.sleep(0.2)
            except KeyError:
              print("Messages may only contain printable ASCII characters.")
    except KeyboardInterrupt:
        # clean up our streams and exit
        stream.stop_stream()
        stream.close()
        p.terminate()
        print("exited cleanly")
