// Pure audio functions, shared by browser and Node tests. No speech synthesis/recognition.
export function resample(samples, inputRate, outputRate = 16000) {
  if (!(samples instanceof Float32Array) || !samples.length || !Number.isFinite(inputRate) || inputRate <= 0 || !Number.isFinite(outputRate) || outputRate <= 0) throw new Error('无效音频采样');
  const count = Math.max(1, Math.floor(samples.length * outputRate / inputRate));
  const result = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    const position = i * inputRate / outputRate;
    const left = Math.min(Math.floor(position), samples.length - 1);
    const right = Math.min(left + 1, samples.length - 1);
    result[i] = samples[left] + (samples[right] - samples[left]) * (position - left);
  }
  return result;
}

export function pcmWav(samples, sampleRate = 16000) {
  if (!(samples instanceof Float32Array) || !samples.length || !Number.isInteger(sampleRate) || sampleRate < 8000 || sampleRate > 48000) throw new Error('无效PCM音频');
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const text = (offset, value) => [...value].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  text(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true); text(8, 'WAVE'); text(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); text(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  samples.forEach((value, i) => {
    const clipped = Math.max(-1, Math.min(1, Number.isFinite(value) ? value : 0));
    view.setInt16(44 + i * 2, Math.round(clipped * (clipped < 0 ? 32768 : 32767)), true);
  });
  return buffer;
}

export function mergeChunks(chunks) {
  const merged = new Float32Array(chunks.reduce((total, chunk) => total + chunk.length, 0));
  let offset = 0;
  for (const chunk of chunks) { merged.set(chunk, offset); offset += chunk.length; }
  return merged;
}

export function base64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(binary);
}
