import os
import random
import struct
import threading
import time
from threading import Thread
from time import sleep

import boto3
import openai
import pvcobra
import pvleopard
import pvporcupine
import pyaudio
import pygame

from recorder import Recorder

polly = boto3.client("polly")

gpt_model = "gpt-3.5-turbo"

picovoice_key = os.getenv("pv_access_key", "no_key")
openai.api_key = os.getenv("openai_access_key", "no_key")

wakeup_words = [
    "computer",
    "jarvis",
]

hal_prompts = [
    "Greetings, Vlad. How may I assist you today?",
    "Hello, Vlad. It's a pleasure to see you again. What can I help you with?",
    "Good day, Vlad. I am here to provide any support you need.",
    "Welcome back, Vlad. How can I be of service to you?",
    "Hi, Vlad. I hope you're having a productive day. What can I do for you?",
    "Hello, Vlad. I'm at your service. What would you like me to do?",
    "Good to see you, Vlad. I'm here to help with any tasks you have.",
    "Hi, Vlad. I trust you are well. How may I help you today?",
    "Greetings, Vlad. It's always a pleasure. How can I be of assistance?",
]

silence_buffer = 2

chat_log = [
    {"role": "system", "content": "You are a helpful assistant."},
]


def voice(prompt):
    voice_response = polly.synthesize_speech(
        Text=prompt, OutputFormat="mp3", VoiceId="Amy"
    )

    if "AudioStream" in voice_response:
        with voice_response["AudioStream"] as stream:
            output_file = "voice.mp3"
            try:
                with open(output_file, "wb") as file:
                    file.write(stream.read())
            except IOError as error:
                print(error)
            pygame.mixer.init()
            pygame.mixer.music.load(output_file)
    else:
        print("Could not stream audio")

    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pass
    sleep(0.2)


def listen():
    cobra = pvcobra.create(access_key=picovoice_key)

    listen_pa = pyaudio.PyAudio()

    listen_audio_stream = listen_pa.open(
        rate=cobra.sample_rate,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=cobra.frame_length,
    )

    print("\nListening...")

    while True:
        listen_pcm = listen_audio_stream.read(cobra.frame_length)
        listen_pcm = struct.unpack_from("h" * cobra.frame_length, listen_pcm)

        if cobra.process(listen_pcm) > 0.3:
            print("\nVoice detected")
            listen_audio_stream.stop_stream()
            listen_audio_stream.close()
            cobra.delete()
            break


def detect_silence():
    cobra = pvcobra.create(access_key=picovoice_key)

    silence_pa = pyaudio.PyAudio()

    cobra_audio_stream = silence_pa.open(
        rate=cobra.sample_rate,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=cobra.frame_length,
    )

    last_voice_time = time.time()

    while True:
        cobra_pcm = cobra_audio_stream.read(cobra.frame_length)
        cobra_pcm = struct.unpack_from("h" * cobra.frame_length, cobra_pcm)

        if cobra.process(cobra_pcm) > 0.2:
            last_voice_time = time.time()
        else:
            silence_duration = time.time() - last_voice_time
            if silence_duration > silence_buffer:
                print("Silence detected\n")
                cobra_audio_stream.stop_stream()
                cobra_audio_stream.close()
                cobra.delete()
                last_voice_time = None
                break


def wakeup_word():
    porcupine = pvporcupine.create(
        keywords=wakeup_words,
        access_key=picovoice_key,
    )

    wakeup_pa = pyaudio.PyAudio()

    porcupine_audio_stream = wakeup_pa.open(
        rate=porcupine.sample_rate,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=porcupine.frame_length,
    )

    detect = True

    while detect:
        porcupine_pcm = porcupine_audio_stream.read(porcupine.frame_length)
        porcupine_pcm = struct.unpack_from("h" * porcupine.frame_length, porcupine_pcm)

        porcupine_keyword_index = porcupine.process(porcupine_pcm)

        if porcupine_keyword_index >= 0:
            print("\nwakeup word received.")
            porcupine_audio_stream.stop_stream()
            porcupine_audio_stream.close()
            porcupine.delete()
            detect = False


def response_printer(response):
    for word in response:
        time.sleep(0.055)
        print(word, end="", flush=True)
    print()


def append_clear_countdown():
    sleep(300)
    global chat_log
    chat_log.clear()
    chat_log = [
        {"role": "system", "content": "You are a helpful assistant."},
    ]
    global count
    count = 0
    t_count.join


def chat_gpt(query):
    chat_log.append({"role": "user", "content": query})
    response = openai.ChatCompletion.create(model=gpt_model, messages=chat_log)

    return str.strip(response["choices"][0]["message"]["content"])


if __name__ == "__main__":
    print("\nHi, this is HAL, Vlad's personal assistant.")
    pvleopard_handle = None

    try:
        pvleopard_handle = pvleopard.create(
            access_key=picovoice_key,
            enable_automatic_punctuation=True,
        )

        count = 0
        event = threading.Event()

        while True:
            if count == 0:
                t_count = threading.Thread(target=append_clear_countdown)
                t_count.start()
            else:
                pass
            count += 1
            wakeup_word()
            voice(random.choice(hal_prompts))
            recorder = Recorder()
            recorder.start()
            listen()
            detect_silence()
            transcript, words = pvleopard_handle.process(recorder.stop())
            recorder.stop()
            print(transcript)
            (res) = chat_gpt(transcript)
            print("\nChatGPT's response is:\n")
            t1 = Thread(target=voice, args=(res,))
            t2 = Thread(target=response_printer, args=(res,))

            t1.start()
            t2.start()

            t1.join()
            t2.join()
            event.set()

            recorder.stop()
            pvleopard_handle.delete()
            recorder = None

    except KeyboardInterrupt:
        print("\nQuiting HalGPT")
        pvleopard_handle.delete()
