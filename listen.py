import Queue
import threading
import time
import pyaudio
import numpy as np
import quietnet
import options
import sys
import psk

FORMAT = pyaudio.paInt16
frame_length = options.frame_length
chunk = options.chunk
rate = options.rate
# sigil = [int(x) for x in options.sigil]
frames_per_buffer = chunk * 10

in_length = 4000
# raw audio frames
in_frames = Queue.Queue(in_length)
# the value of the fft at the frequency we care about
points = Queue.Queue(in_length)
bits = Queue.Queue(in_length / frame_length)
recieved_bytes = Queue.Queue(1024)

wait_for_sample_timeout = 0.1
wait_for_frames_timeout = 0.1
wait_for_point_timeout = 0.1
wait_for_byte_timeout = 0.1

# yeeeep this is just hard coded
bottom_threshold = 5000

DECODE = {
    0: 1,
    1: None,
    2: 0
}


def process_frames(tones):
    ONE, SIGIL, ZERO = (
            tones[1],
            tones[None],
            tones[0]
            )

    unpack = lambda p: (
                quietnet.has_freq(p, ONE, rate, chunk),
                quietnet.has_freq(p, SIGIL, rate, chunk),
                quietnet.has_freq(p, ZERO, rate, chunk)
                )

    while True:
        try:
            frame = in_frames.get(False)
            fft = quietnet.fft(frame)
            points.put(unpack(fft))
        except Queue.Empty:
            time.sleep(wait_for_frames_timeout)


def normalise(points):
    return (
        np.average(map(lambda p: p[0], points)),
        np.average(map(lambda p: p[1], points)),
        np.average(map(lambda p: p[2], points)),
    )


def process_points():
    while True:
        cur_points = []
        while len(cur_points) < frame_length:
            try:
                cur_points.append(points.get(False))
            except Queue.Empty:
                time.sleep(wait_for_point_timeout)

        ring = 0
        while True:
            best = 0
            while best < bottom_threshold:
                norm = normalise(cur_points)
                best = max(norm)
                try:
                    ring <<= 1
                    if ring & 0b1111 == 0:
                        sent = False
                    cur_points.append(points.get(False))
                    cur_points.pop(0)
                except Queue.Empty:
                    time.sleep(wait_for_point_timeout)
            ring |= 1
            ring &= 0xff

            idx = norm.index(best)
            if ring & 0b11 == 0b11 and not sent:
                sent = True
                bits.put(DECODE[idx])
                print("Got a %s" % DECODE[idx])

def process_bits():
    _bits = []
    while True:
        continue
        cur_bits = []
        # while the last two characters are not the sigil
        while len(cur_bits) < len(sigil) or cur_bits[-len(sigil):len(cur_bits)] != sigil:
            try:
                cur_bits.append(bits.get(False))
            except Queue.Empty:
                time.sleep(wait_for_byte_timeout)
        if cur_bits == sigil:
            continue
        # Oh god, really?
        cur_bits = cur_bits[:-len(sigil)]
        cur_bits = filter(lambda x: x, cur_bits)

        if len(cur_bits) < 2:
            continue
        elif len(cur_bits) > 9:
            if len(cur_bits) > 27:
                print "WARNING: Probably just doubled a byte :<"
                if len(cur_bits) > 35:
                    print "Assuming doubled bits were both 1"
                    _bits.insert(0, 1)
                else:
                    print "Taking a punt on ordering"
                    _bits.insert(0, 0)
            _bits.insert(0, 1)
        else:
            _bits.insert(0, 0)

        if len(_bits) >= 8:
            # Got a whole byte! Maybe even more than one!
            operative_bits, _bits = _bits[-8:], _bits[8:]
            byte = 0
            for idx, i in enumerate(operative_bits):
                byte |= i << idx
            recieved_bytes.put(chr(byte))
            # sys.stdout.write(chr(byte))
            # sys.stdout.flush()
        # sys.stdout.write(psk.decode(cur_bits[:-len(sigil)]))

quiet = False
def main():
    setup_processes()
    if not quiet:
        sys.stdout.write("Quietnet listening at %sHz\n" % search_freq)
        sys.stdout.flush()
    for char in start_analysing_stream():
        print char

def setup_processes(tones):
    # start the queue processing threads
    processes = [lambda: process_frames(tones),
            process_points, process_bits]

    for process in processes:
        thread = threading.Thread(target=process)
        thread.daemon = True
        thread.start()


def callback(in_data, frame_count, time_info, status):
    frames = list(quietnet.chunks(quietnet.unpack(in_data), chunk))
    for frame in frames:
        if not in_frames.full():
            in_frames.put(frame, False)
    return (in_data, pyaudio.paContinue)

def start_analysing_stream():
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=options.channels, rate=options.rate,
        input=True, frames_per_buffer=frames_per_buffer, stream_callback=callback)
    stream.start_stream()
    while stream.is_active():
        try:
            yield recieved_bytes.get(False)
        except Queue.Empty:
            time.sleep(wait_for_sample_timeout)


if __name__ == '__main__':
    if "-q" in sys.argv:
        sys.argv.pop(sys.argv.index("-q"))
        quiet = True
    if len(sys.argv) > 1:
        freq = int(sys.argv[1])
    main()
