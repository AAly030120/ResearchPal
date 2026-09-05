const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const DEFAULT_TIMEOUT = 15000; // 15s 默认超时（文件上传/设置等轻量请求）
const AI_TIMEOUT = 120000;     // 120s LLM 重任务超时（总结/PPT/分析/代码生成/翻译）
const CHUNK_SIZE = 5 * 1024 * 1024; // 5 MB
const AI_CONCURRENCY_LIMIT = 3;     // AI 请求最大并发数

// ── AI 并发控制 ─────────────────────────────────────────────────────
let _aiRunning = 0;
const _aiQueue: Array<() => void> = [];

function _aiSlotAcquire(): Promise<void> {
  return new Promise((resolve) => {
    if (_aiRunning < AI_CONCURRENCY_LIMIT) {
      _aiRunning++;
      resolve();
    } else {
      _aiQueue.push(() => { _aiRunning++; resolve(); });
    }
  });
}

function _aiSlotRelease(): void {
  _aiRunning--;
  const next = _aiQueue.shift();
  if (next) next();
}

function extractErrorMessage(data: any): string {
  if (!data) return 'Request failed';
  if (data.detail && Array.isArray(data.detail)) {
    return data.detail.map((e: any) => `${e.loc?.join('.') || 'field'}: ${e.msg}`).join('; ');
  }
  if (typeof data.detail === 'string') return data.detail;
  if (typeof data.message === 'string') return data.message;
  return 'Request failed';
}

function fetchWithTimeout(url: string, options: RequestInit, timeoutMs: number): Promise<Response> {
  if (!timeoutMs) return fetch(url, options);
  return new Promise((resolve, reject) => {
    const controller = new AbortController();
    const existingSignal = options.signal;
    if (existingSignal) {
      existingSignal.addEventListener('abort', () => controller.abort());
    }
    const timeoutId = setTimeout(() => {
      controller.abort();
      reject(new Error('请求超时，请检查后端服务是否运行'));
    }, timeoutMs);

    fetch(url, { ...options, signal: controller.signal })
      .then((res) => { clearTimeout(timeoutId); resolve(res); })
      .catch((err) => {
        clearTimeout(timeoutId);
        if (err.name === 'AbortError') {
          reject(new Error('请求超时，请检查后端服务是否运行'));
        } else {
          reject(err);
        }
      });
  });
}

class ApiClient {
  private getToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('access_token');
  }

  async fetch(endpoint: string, options: RequestInit = {}, timeoutMs?: number): Promise<Response> {
    const token = this.getToken();
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string> || {}),
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }
    const res = await fetchWithTimeout(`${API_BASE}${endpoint}`, { ...options, headers }, timeoutMs ?? DEFAULT_TIMEOUT);
    if (res.status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
      if (typeof window !== 'undefined' && !window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
    }
    return res;
  }

  async get(endpoint: string) {
    const res = await this.fetch(endpoint);
    const data = await res.json();
    if (!res.ok) throw new Error(extractErrorMessage(data));
    return data;
  }

  async post(endpoint: string, data?: any, isFormData = false, timeoutMs?: number) {
    const body = isFormData ? data : JSON.stringify(data);
    const res = await this.fetch(endpoint, {
      method: 'POST',
      body,
      headers: isFormData ? {} : { 'Content-Type': 'application/json' },
    }, timeoutMs);
    const json = await res.json();
    if (!res.ok) throw new Error(extractErrorMessage(json));
    return json;
  }

  async patch(endpoint: string, data: any) {
    const res = await this.fetch(endpoint, { method: 'PATCH', body: JSON.stringify(data) });
    const json = await res.json();
    if (!res.ok) throw new Error(extractErrorMessage(json));
    return json;
  }

  async delete(endpoint: string) {
    const res = await this.fetch(endpoint, { method: 'DELETE' });
    if (res.status === 204) return {};
    const json = await res.json();
    if (!res.ok) throw new Error(extractErrorMessage(json));
    return json;
  }

  async upload(endpoint: string, formData: FormData) {
    return this.post(endpoint, formData, true);
  }

  // ── Chunked Upload with real progress ─────────────────────────────────

  /**
   * Upload a file in chunks with real-time progress.
   * @param file          The File object to upload
   * @param onProgress    Callback with 0-100 percentage
   * @returns             The FileResponse JSON from the server
   */
  async uploadWithProgress(
    file: File,
    onProgress?: (pct: number) => void,
  ): Promise<{ id: string; original_name: string; file_type: string; file_size: number }> {
    // For small files, use simple upload with XHR progress
    if (file.size <= CHUNK_SIZE) {
      return this._simpleUploadWithProgress(file, onProgress);
    }
    return this._chunkedUpload(file, onProgress);
  }

  private _simpleUploadWithProgress(file: File, onProgress?: (pct: number) => void): Promise<any> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const formData = new FormData();
      formData.append('file', file);

      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable && onProgress) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      });

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try { resolve(JSON.parse(xhr.responseText)); }
          catch { reject(new Error('Invalid server response')); }
        } else {
          try {
            const err = JSON.parse(xhr.responseText);
            reject(new Error(extractErrorMessage(err)));
          } catch {
            reject(new Error(`Upload failed (${xhr.status})`));
          }
        }
      });

      xhr.addEventListener('error', () => reject(new Error('Network error during upload')));
      xhr.addEventListener('abort', () => reject(new Error('Upload aborted')));

      xhr.open('POST', `${API_BASE}/api/files/upload`);
      const token = this.getToken();
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      xhr.send(formData);
    });
  }

  private async _chunkedUpload(file: File, onProgress?: (pct: number) => void): Promise<any> {
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    const token = this.getToken();

    // Step 1: Start chunked upload session
    const startRes = await this.fetch('/api/files/chunk/start', {
      method: 'POST',
      body: JSON.stringify({ filename: file.name, file_size: file.size, total_chunks: totalChunks }),
    });
    const startData = await startRes.json();
    if (!startRes.ok) throw new Error(extractErrorMessage(startData));
    const uploadId = startData.upload_id;

    // Step 2: Upload each chunk with progress
    let uploadedBytes = 0;
    for (let i = 0; i < totalChunks; i++) {
      const start = i * CHUNK_SIZE;
      const end = Math.min(start + CHUNK_SIZE, file.size);
      const chunk = file.slice(start, end);

      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const formData = new FormData();
        formData.append('chunk', chunk, `chunk-${i}`);

        xhr.addEventListener('load', () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            uploadedBytes += (end - start);
            if (onProgress) onProgress(Math.round((uploadedBytes / file.size) * 100));
            resolve();
          } else {
            reject(new Error(`Chunk ${i} failed (${xhr.status})`));
          }
        });
        xhr.addEventListener('error', () => reject(new Error(`Chunk ${i} network error`)));
        xhr.addEventListener('abort', () => reject(new Error('Upload aborted')));

        xhr.open('POST', `${API_BASE}/api/files/chunk/${uploadId}?chunk_index=${i}`);
        if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        xhr.send(formData);
      });
    }

    // Step 3: Complete and merge
    const completeRes = await this.fetch('/api/files/chunk/complete', {
      method: 'POST',
      body: JSON.stringify({ upload_id: uploadId }),
    });
    const completeData = await completeRes.json();
    if (!completeRes.ok) throw new Error(extractErrorMessage(completeData));
    return completeData;
  }

  // ── AI 并发控制 ────────────────────────────────────────────────────

  /** Wrap an AI-intensive async call with concurrency limiting */
  async withAiSlot<T>(fn: () => Promise<T>): Promise<T> {
    await _aiSlotAcquire();
    try {
      return await fn();
    } finally {
      _aiSlotRelease();
    }
  }

  get aiRunning(): number { return _aiRunning; }
  get aiQueueLength(): number { return _aiQueue.length; }

  // ── URL helpers ────────────────────────────────────────────────────

  getDownloadUrl(fileId: string): string {
    return `${API_BASE}/api/files/download/${fileId}`;
  }

  getPreviewUrl(fileId: string): string {
    return `${API_BASE}/api/files/preview/${fileId}`;
  }

  getTaskDownloadUrl(taskId: string): string {
    return `${API_BASE}/api/tasks/${taskId}/download`;
  }

  // ── Settings / API Keys ────────────────────────────────────────────

  // ── Password Reset ─────────────────────────────────────────────────

  async forgotPassword(email: string): Promise<{ message: string; reset_url: string | null; reset_token?: string; demo_note?: string }> {
    return this.post('/api/auth/forgot-password', { email });
  }

  async resetPassword(token: string, newPassword: string): Promise<{ message: string }> {
    return this.post('/api/auth/reset-password', { token, new_password: newPassword });
  }

  // ── Settings / API Keys ──────────────────────────────────────────── (continued)

  async getApiKeyStatus(): Promise<Array<{ key_env: string; configured: boolean; masked: string; label: string }>> {
    return this.get('/api/settings/keys');
  }

  async setApiKey(keyEnv: string, value: string): Promise<any> {
    return this.fetch('/api/settings/keys', {
      method: 'PUT',
      body: JSON.stringify({ key_env: keyEnv, value }),
    }).then(async (res) => {
      const json = await res.json();
      if (!res.ok) throw new Error(extractErrorMessage(json));
      return json;
    });
  }

  async deleteApiKey(keyEnv: string): Promise<any> {
    return this.delete(`/api/settings/keys/${keyEnv}`);
  }

  async getModelsStatus(): Promise<{ models: Array<any>; demo_mode: boolean; message: string }> {
    return this.get('/api/settings/models');
  }

  // ── Streaming ──────────────────────────────────────────────────────

  streamChat(
    endpoint: string,
    data: any,
    onChunk: (text: string) => void,
    onDone: (convId?: string, retrievedCount?: number) => void,
    onError: (err: string) => void,
    signal?: AbortSignal,
  ): AbortController {
    const token = this.getToken();
    const controller = signal ? null : new AbortController();
    const effectiveSignal = signal || controller!.signal;

    (async () => {
      try {
        const res = await fetch(`${API_BASE}${endpoint}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify(data),
          signal: effectiveSignal,
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          onError(extractErrorMessage(err));
          return;
        }
        const reader = res.body?.getReader();
        const decoder = new TextDecoder();
        if (reader) {
          let buffer = '';
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const raw = line.slice(6);
                try {
                  const parsed = JSON.parse(raw);
                  if (parsed.chunk) onChunk(parsed.chunk);
                  if (parsed.done) onDone(parsed.conversation_id, parsed.retrieved_count);
                  if (parsed.error && parsed.chunk) onError(parsed.chunk);
                } catch {}
              }
            }
          }
        }
      } catch (err: any) {
        if (err.name === 'AbortError') return;
        onError(err.message || 'Connection failed');
      }
    })();

    return controller!;
  }
}

export const api = new ApiClient();
