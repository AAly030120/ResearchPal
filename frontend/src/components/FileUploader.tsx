'use client';
import { useState, useRef, useCallback } from 'react';
import { api } from '@/lib/api';
import { t } from '@/lib/i18n';

interface FileUploaderProps {
  onUpload: (fileId: string) => void;
  onUploadDetail?: (detail: { id: string; name: string; type: string; size: number }) => void;
  accept?: string;
}

export default function FileUploader({ onUpload, onUploadDetail, accept }: FileUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [uploadMode, setUploadMode] = useState<'simple' | 'chunked'>('simple');
  const [error, setError] = useState<string | null>(null);
  const [uploadedFile, setUploadedFile] = useState<{ name: string; id: string; type: string; size: number } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleFile = useCallback(async (file: File) => {
    setError(null);

    if (file.size > 50 * 1024 * 1024) {
      setError('文件大小不能超过 50MB');
      return;
    }

    setUploading(true);
    setProgress(0);
    setUploadMode(file.size > 5 * 1024 * 1024 ? 'chunked' : 'simple');

    try {
      const data = await api.uploadWithProgress(file, (pct) => {
        setProgress(pct);
      });

      const fileId = data.id || data.file_id;
      const fileName = data.original_name || file.name;
      const fileType = data.file_type || file.name.split('.').pop() || '';
      const fileSize = data.file_size || file.size;

      setUploadedFile({ name: fileName, id: fileId, type: fileType, size: fileSize });
      setProgress(100);
      onUpload(fileId);
      if (onUploadDetail) {
        onUploadDetail({ id: fileId, name: fileName, type: fileType, size: fileSize });
      }
    } catch (err: any) {
      setError(err.message || '上传失败');
    } finally {
      setUploading(false);
    }
  }, [onUpload, onUploadDetail]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

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
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div className="w-full">
      <div
        onClick={handleClick}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
          isDragging
            ? 'border-indigo-400 bg-indigo-50'
            : uploadedFile
            ? 'border-green-300 bg-green-50'
            : 'border-gray-300 hover:border-indigo-300 bg-gray-50'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept={accept}
          onChange={handleChange}
        />

        {uploadedFile ? (
          <div className="space-y-2">
            <div className="text-3xl">✅</div>
            <p className="text-sm font-medium text-green-700">{uploadedFile.name}</p>
            <p className="text-xs text-green-500">
              {formatSize(uploadedFile.size)} · {uploadedFile.type.toUpperCase()}
            </p>
          </div>
        ) : uploading ? (
          <div className="space-y-3">
            <div className="text-3xl animate-pulse">⏳</div>
            <p className="text-sm text-indigo-600 font-medium">
              {uploadMode === 'chunked' ? '分片上传中...' : '上传中...'}
            </p>
            {/* Progress bar */}
            <div className="w-full max-w-xs mx-auto">
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>{progress}%</span>
                <span>{uploadMode === 'chunked' ? `${Math.ceil(progress / 100 * 100)}%` : ''}</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
                <div
                  className="h-2.5 rounded-full transition-all duration-200 ease-out"
                  style={{
                    width: `${progress}%`,
                    background: progress < 100
                      ? 'linear-gradient(90deg, #6366f1, #818cf8)'
                      : '#22c55e',
                  }}
                />
              </div>
              {uploadMode === 'chunked' && (
                <p className="text-xs text-gray-400 mt-1">大文件分片传输中...</p>
              )}
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="text-4xl">📄</div>
            <p className="text-sm font-medium text-gray-600">{t('upload.drop')}</p>
            <p className="text-xs text-gray-400">{t('upload.limit')}</p>
          </div>
        )}
      </div>

      {error && (
        <p className="mt-2 text-sm text-red-600">{error}</p>
      )}
    </div>
  );
}
