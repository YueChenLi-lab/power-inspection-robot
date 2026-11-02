class PCMCollector extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(8192); this.offset = 0; this.done = false;
    this.port.onmessage = event => {
      if (event.data === 'flush') { this.flush(); this.done = true; this.port.postMessage({flushed: true}); }
    };
  }
  flush() {
    if (this.offset) {
      const chunk = this.buffer.slice(0, this.offset);
      this.port.postMessage({pcm: chunk}, [chunk.buffer]); this.offset = 0;
    }
  }
  process(inputs) {
    if (this.done) return false;
    const channels = inputs[0];
    if (!channels || !channels.length) return true;
    for (let i = 0; i < channels[0].length; i++) {
      let sample = 0;
      for (const channel of channels) sample += channel[i];
      this.buffer[this.offset++] = sample / channels.length;
      if (this.offset === this.buffer.length) this.flush();
    }
    return true;
  }
}
registerProcessor('pcm-collector', PCMCollector);
