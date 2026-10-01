export interface BenchmarkReceipt {
  schema_version: 1;
  lane: "coimbra-034-webgpu-feasibility";
  generated_at: string;
  renderer: string;
  webgpu_available: boolean;
  user_agent: string;
  viewport_css: [number, number];
  device_pixel_ratio: number;
  mode: string;
  sample_count: number;
  mean_frame_ms: number;
  p50_frame_ms: number;
  p95_frame_ms: number;
  max_frame_ms: number;
  fps_from_mean: number;
  frames_over_50ms: number;
}

function percentile(values: number[], p: number) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * p));
  return sorted[index];
}

export class PerfMeter {
  private samples: number[] = [];

  push(ms: number) {
    if (Number.isFinite(ms) && ms > 0 && ms < 1000) this.samples.push(ms);
    if (this.samples.length > 3600) this.samples.splice(0, this.samples.length - 3600);
  }

  reset() {
    this.samples = [];
  }

  receipt(mode: string): BenchmarkReceipt {
    const values = this.samples.slice();
    const mean = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
    return {
      schema_version: 1,
      lane: "coimbra-034-webgpu-feasibility",
      generated_at: new Date().toISOString(),
      renderer: "three.js WebGPURenderer",
      webgpu_available: "gpu" in navigator,
      user_agent: navigator.userAgent,
      viewport_css: [innerWidth, innerHeight],
      device_pixel_ratio: devicePixelRatio,
      mode,
      sample_count: values.length,
      mean_frame_ms: Number(mean.toFixed(3)),
      p50_frame_ms: Number(percentile(values, 0.50).toFixed(3)),
      p95_frame_ms: Number(percentile(values, 0.95).toFixed(3)),
      max_frame_ms: Number((values.length ? Math.max(...values) : 0).toFixed(3)),
      fps_from_mean: Number((mean > 0 ? 1000 / mean : 0).toFixed(2)),
      frames_over_50ms: values.filter((value) => value > 50).length,
    };
  }
}

export function downloadReceipt(receipt: BenchmarkReceipt) {
  const blob = new Blob([JSON.stringify(receipt, null, 2) + "\n"], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "coimbra-034-webgpu-benchmark.json";
  link.click();
  URL.revokeObjectURL(url);
}


export interface WebGpuAdapterInfo {
  available: boolean;
  vendor?: string;
  architecture?: string;
  device?: string;
  description?: string;
  is_fallback_adapter?: boolean | null;
}

export async function collectWebGpuAdapterInfo(): Promise<WebGpuAdapterInfo> {
  type Adapter = {
    info?: {
      vendor?: string;
      architecture?: string;
      device?: string;
      description?: string;
    };
    isFallbackAdapter?: boolean;
  };
  type GpuNavigator = Navigator & {
    gpu?: {
      requestAdapter(options?: { powerPreference?: "low-power" | "high-performance" }): Promise<Adapter | null>;
    };
  };

  const gpu = (navigator as GpuNavigator).gpu;
  if (!gpu) return { available: false };
  const adapter = await gpu.requestAdapter({ powerPreference: "high-performance" });
  if (!adapter) return { available: false };

  const info = adapter.info ?? {};
  return {
    available: true,
    vendor: info.vendor,
    architecture: info.architecture,
    device: info.device,
    description: info.description,
    is_fallback_adapter: adapter.isFallbackAdapter ?? null,
  };
}
