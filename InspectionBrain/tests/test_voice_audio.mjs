import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {resample, pcmWav, mergeChunks, base64} from '../voice_lab/static/audio.js';

test('WAV is mono PCM16 at 16kHz and clips without wraparound', () => {
  const wav = pcmWav(new Float32Array([-2, -1, 0, 1, 2, NaN]));
  const view = new DataView(wav);
  assert.equal(new TextDecoder().decode(wav.slice(0, 4)), 'RIFF');
  assert.equal(view.getUint32(4, true), wav.byteLength - 8);
  assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint32(24, true), 16000);
  assert.equal(view.getUint16(34, true), 16);
  assert.deepEqual(Array.from({length: 6}, (_, i) => view.getInt16(44 + i * 2, true)), [-32768, -32768, 0, 32767, 32767, 0]);
});
test('48k and 44.1k capture resamples to a bounded 16k frame count', () => {
  for (const rate of [48000, 44100, 16000]) {
    const result = resample(new Float32Array(rate).fill(.5), rate);
    assert.equal(result.length, 16000); assert.equal(result[8000], .5);
  }
  assert.throws(() => resample(new Float32Array(), 48000));
  assert.throws(() => pcmWav(new Float32Array()));
});
test('chunk joining and base64 preserve original byte order', () => {
  assert.deepEqual([...mergeChunks([new Float32Array([1, 2]), new Float32Array([3])])], [1, 2, 3]);
  assert.equal(base64(new Uint8Array([0, 128, 255]).buffer), 'AID/');
});
test('AudioWorklet averages channels and flushes the final partial buffer exactly once', async () => {
  const messages = [];
  let Processor;
  class Base { constructor() { this.port = {postMessage: message => messages.push(message)}; } }
  const context = vm.createContext({Float32Array, AudioWorkletProcessor: Base, registerProcessor: (name, klass) => { Processor = klass; }});
  vm.runInContext(await readFile(new URL('../voice_lab/static/pcm-worklet.js', import.meta.url), 'utf8'), context);
  const processor = new Processor();
  processor.process([[new Float32Array([1, .5]), new Float32Array([-1, .5])]]);
  processor.port.onmessage({data: 'flush'});
  assert.deepEqual([...messages[0].pcm], [0, .5]);
  assert.equal(messages[1].flushed, true);
  assert.equal(processor.process([[new Float32Array([1])]]), false);
});
