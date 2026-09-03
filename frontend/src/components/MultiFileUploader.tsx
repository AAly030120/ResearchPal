'use client';
import { useState, useRef, useCallback } from 'react';
import { api } from '@/lib/api';

export interface UploadedFile {
  id: string;
  name: string;
  type: string;
  size?: number;
  uploading: boolean;
  progress?: number;   // 0-100
  uploadMode?: 'simple' | 'chunked';
}

interface MultiFileUploaderProps {
  onFilesChange: (files: UploadedFile[]) => void;
  accept?: string;
  maxFiles?: number;
}

const CONCURRENCY_LIMIT = 3;   // 同时最多上传 3 个文件

export default function MultiFileUploader({ onFilesChange, accept, maxFiles = 15 }: MultiFileUploaderProps) {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const filesRef = useRef<UploadedFile[]>([]);
  const queueRef = useRef<File[]>([]);
  const runningRef = useRef(0);

  const notifyParent = useCallback((updatedFiles: UploadedFile[]) => {
    setFiles(updatedFiles);
    filesRef.current = updatedFiles;
    onFilesChange(updatedFiles);
  }, [onFilesChange]);

  /** Upload a single file via chunked/simple path with progress */
  const uploadOne = useCallback(async (file: File, index: number): Promise<void> => {
    const updateProgress = (pct: number) => {
      const current = [...filesRef.current];
      if (current[index]) {
        current[index] = {
          ...current[index],
          progress: pct,
          uploadMode: file.size > 5 * 1024 * 1024 ? 'chunked' : 'simple',
        };
        notifyParent(current);
      }
    };

    try {
      const data = await api.uploadWithProgress(file, updateProgress);
      const current = [...filesRef.current];
      if (current[index]) {
        current[index] = {
          id: data.id || data.file_id,
          name: data.original_name || file.name,
          type: data.file_type || file.name.split('.').pop()?.toLowerCase() || '',
          size: data.file_size || file.size,
          uploading: false,
          progress: 100,
        };
        notifyParent(current);
      }
    } catch (err: any) {
      const current = [...filesRef.current];
      if (current[index]) {
        current[index] = {
          ...current[index],
          uploading: false,
          progress: undefined,
        };
        notifyParent(current);
      }
      setErrors(prev => [...prev, `${file.name}: ${err.message}`]);
    }
  }, [notifyParent]);

  /** Process the next file in the queue */
  const processQueue = useCallback(() => {
    const processNext = () => {
      if (queueRef.current.length === 0 || runningRef.current >= CONCURRENCY_LIMIT) return;

      const file = queueRef.current.shift()!;
      runningRef.current++;

      const placeholder: UploadedFile = {
        id: '',
        name: file.name,
        type: file.name.split('.').pop()?.toLowerCase() || '',
        uploading: true,
        progress: 0,
      };

      const current = [...filesRef.current, placeholder];
      const idx = current.length - 1;
      notifyParent(current);

      uploadOne(file, idx).finally(() => {
        runningRef.current--;
        processNext();
      });

      // Start another if slots available
      processNext();
    };

    // Kick off up to CONCURRENCY_LIMIT
    for (let i = 0; i < CONCURRENCY_LIMIT; i++) {
      processNext();
    }
  }, [notifyParent, uploadOne]);

  /** Add files to the upload queue */
  const addFiles = useCallback((newFiles: File[]) => {
    setErrors([]);

    for (const file of newFiles) {
      if (filesRef.current.length + queueRef.current.length >= maxFiles) {
        setErrors(prev => [...prev, `最多上传 ${maxFiles} 个文件`]);
        break;
      }
      if (file.size > 50 * 1024 * 1024) {
        setErrors(prev => [...prev, `文件 ${file.name} 超过 50MB 限制`]);
        continue;
      }
      queueRef.current.push(file);
    }

    processQueue();
  }, [maxFiles, processQueue]);

  const removeFile = useCallback((index: number) => {
    const updated = filesRef.current.filter((_, i) => i !== index);
    notifyParent(updated);
  }, [notifyParent]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    addFiles(Array.from(e.dataTransfer.files));
  }, [addFiles]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleClick = () => fileInputRef.current?.click();

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(Array.from(e.target.files));
    }
    e.target.value = '';
  };

  const totalUploading = files.filter(f => f.uploading).length;

  return (
    <div className="w-full space-y-3">
      {/* Drop zone */}
      <div
        onClick={handleClick}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`relative border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition-colors ${
          isDragging
            ? 'border-indigo-400 bg-indigo-50'
            : 'border-gray-300 hover:border-indigo-300 bg-gray-50'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept={accept}
          multiple
          onChange={handleChange}
        />
        <div className="space-y-1">
          <div className="text-2xl">📁</div>
          <p className="text-sm font-medium text-gray-600">拖拽文件到此处，或点击选择</p>
          <p className="text-xs text-gray-400">
            支持多文件并行上传（最多 {CONCURRENCY_LIMIT} 个同时），每个文件不超过 50MB
          </p>
          {totalUploading > 0 && (
            <p className="text-xs text-indigo-600 font-medium">
              {totalUploading} 个文件上传中...
            </p>
          )}
          {files.filter(f => !f.uploading).length > 0 && (
            <p className="text-xs text-green-600">
              {files.filter(f => !f.uploading).length} 个文件已就绪
            </p>
          )}
        </div>
      </div>

      {errors.length > 0 && (
        <div className="space-y-1">
          {errors.map((err, i) => (
            <p key={i} className="text-sm text-red-600">{err}</p>
          ))}
        </div>
      )}

      {/* File list with individual progress bars */}
      {files.length > 0 && (
        <div className="space-y-2">
          {files.map((file, i) => (
            <div
              key={`${file.name}-${i}`}
              className={`flex items-center justify-between p-2.5 rounded-lg border text-sm ${
                file.uploading
                  ? 'border-indigo-200 bg-indigo-50/60'
                  : 'border-green-200 bg-green-50'
              }`}
            >
              <div className="flex items-center gap-2 min-w-0 flex-1">
                {file.uploading ? (
                  file.progress !== undefined && file.progress < 100 ? (
                    /* Individual progress bar */
                    <div className="flex-1 min-w-0 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="truncate text-gray-700 text-xs" title={file.name}>
                          {file.name}
                        </span>
                        <span className="text-xs text-indigo-500 font-medium ml-2 flex-shrink-0">
                          {file.progress}%
                        </span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden">
                        <div
                          className="h-1.5 rounded-full bg-indigo-500 transition-all duration-200"
                          style={{ width: `${file.progress}%` }}
                        />
                      </div>
                      <span className="text-[10px] text-gray-400">
                        {file.uploadMode === 'chunked' ? '分片传输' : '直接上传'}
                      </span>
                    </div>
                  ) : (
                    <>
                      <div className="animate-spin h-3.5 w-3.5 border-2 border-indigo-400 border-t-transparent rounded-full flex-shrink-0" />
                      <span className="truncate text-gray-700">{file.name}</span>
                    </>
                  )
                ) : (
                  <>
                    <span className="text-green-600 text-sm flex-shrink-0">✓</span>
                    <span className="truncate text-gray-700" title={file.name}>
                      {file.name}
                    </span>
                    <span className="text-[10px] text-gray-400 bg-white px-1.5 py-0.5 rounded flex-shrink-0">
                      {file.type}
                    </span>
                    {file.size && (
                      <span className="text-[10px] text-gray-400 flex-shrink-0">
                        {file.size < 1024 * 1024
                          ? `${(file.size / 1024).toFixed(0)} KB`
                          : `${(file.size / (1024 * 1024)).toFixed(1)} MB`}
                      </span>
                    )}
                  </>
                )}
              </div>
              {!file.uploading && (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                  className="ml-2 text-gray-400 hover:text-red-500 transition-colors flex-shrink-0"
                  title="移除"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
