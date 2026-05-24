/**
 * Chat Input Component
 * Text area with send button, cancel functionality for streaming, image upload, and optional features toggle
 */

import { useState, useRef, useEffect, type KeyboardEvent, type ChangeEvent } from 'react';
import { SendHorizontal, Square, Globe, Paperclip, X } from 'lucide-react';
import type { ImageData } from '../../types';

/** Extra options that can be enabled per message */
export interface ExtraOptions {
  web_search?: boolean;
  // Future extensibility
  // deep_reasoning?: boolean;
  // multimodal?: boolean;
}

export interface ChatInputProps {
  onSend: (message: string, extraOptions?: ExtraOptions, images?: ImageData[]) => void;
  onCancel?: () => void;
  disabled?: boolean;
  isStreaming?: boolean;
  placeholder?: string;
  externalValue?: string;
  onExternalValueConsumed?: () => void;
}

const MAX_IMAGES = 4;
const MAX_IMAGE_SIZE_MB = 10;
const SUPPORTED_FORMATS = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];

export function ChatInput({ 
  onSend, 
  onCancel,
  disabled = false, 
  isStreaming = false,
  placeholder = 'Type a message...', 
  externalValue,
  onExternalValueConsumed,
}: ChatInputProps) {
  const [input, setInput] = useState('');
  const [isComposing, setIsComposing] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [images, setImages] = useState<ImageData[]>([]);
  const [imagePreviewUrls, setImagePreviewUrls] = useState<string[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Handle external value (from SuggestionChip)
  useEffect(() => {
    if (externalValue !== undefined && externalValue !== '') {
      setInput(externalValue);
      onExternalValueConsumed?.();
      // Focus the textarea
      textareaRef.current?.focus();
    }
  }, [externalValue, onExternalValueConsumed]);

  // Cleanup preview URLs on unmount
  useEffect(() => {
    return () => {
      imagePreviewUrls.forEach(url => URL.revokeObjectURL(url));
    };
  }, [imagePreviewUrls]);

  const handleSend = () => {
    if ((input.trim() || images.length > 0) && !disabled && !isStreaming) {
      const extraOptions: ExtraOptions = {};
      if (webSearchEnabled) {
        extraOptions.web_search = true;
      }
      onSend(
        input,
        Object.keys(extraOptions).length > 0 ? extraOptions : undefined,
        images.length > 0 ? images : undefined
      );
      setInput('');
      setImages([]);
      imagePreviewUrls.forEach(url => URL.revokeObjectURL(url));
      setImagePreviewUrls([]);
      
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleCancel = () => {
    onCancel?.();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    
    // Auto-resize textarea
    const textarea = e.target;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
  };

  const handleImageClick = () => {
    fileInputRef.current?.click();
  };

  /**
   * Process files (images) and add them to the state
   */
  const processFiles = async (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    const newImages: ImageData[] = [];
    const newPreviewUrls: string[] = [];

    for (let i = 0; i < fileArray.length && images.length + newImages.length < MAX_IMAGES; i++) {
      const file = fileArray[i];
      
      // Validate file type
      if (!SUPPORTED_FORMATS.includes(file.type)) {
        console.warn(`Unsupported image format: ${file.type}`);
        continue;
      }

      // Validate file size
      if (file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024) {
        console.warn(`Image too large: ${file.size / 1024 / 1024}MB`);
        continue;
      }

      try {
        // Convert to base64
        const base64 = await fileToBase64(file);
        newImages.push({
          data: base64.split(',')[1], // Remove data URL prefix
          mime_type: file.type,
        });
        newPreviewUrls.push(URL.createObjectURL(file));
      } catch (err) {
        console.error('Error processing image:', err);
      }
    }

    if (newImages.length > 0) {
      setImages(prev => [...prev, ...newImages]);
      setImagePreviewUrls(prev => [...prev, ...newPreviewUrls]);
    }
  };

  /**
   * Handle paste event to support pasting images from clipboard
   */
  const handlePaste = async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items;
    if (!items) return;

    const imageFiles: File[] = [];
    
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) {
          imageFiles.push(file);
        }
      }
    }

    if (imageFiles.length > 0) {
      // Prevent default text paste behavior for images
      e.preventDefault();
      await processFiles(imageFiles);
    }
  };

  const handleFileChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    await processFiles(files);

    // Reset file input
    e.target.value = '';
  };

  const removeImage = (index: number) => {
    URL.revokeObjectURL(imagePreviewUrls[index]);
    setImages(prev => prev.filter((_, i) => i !== index));
    setImagePreviewUrls(prev => prev.filter((_, i) => i !== index));
  };

  const canSend = (input.trim() || images.length > 0) && !disabled && !isStreaming;

  return (
    <div className="relative">
      {/* Feature toggles row */}
      <div className="flex items-center gap-2 mb-2">
        <button
          onClick={() => setWebSearchEnabled(!webSearchEnabled)}
          className={`
            inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
            transition-all duration-200 border
            ${webSearchEnabled
              ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-800'
              : 'bg-gray-50 dark:bg-gray-800 text-gray-500 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700'
            }
          `}
          title={webSearchEnabled ? 'Web Search enabled' : 'Enable Web Search'}
          aria-label={webSearchEnabled ? 'Disable Web Search' : 'Enable Web Search'}
        >
          <Globe className="w-3.5 h-3.5" />
          <span>Web Search</span>
          {webSearchEnabled && (
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
          )}
        </button>
      </div>
      
      {/* Image previews */}
      {imagePreviewUrls.length > 0 && (
        <div className="flex gap-2 mb-2 flex-wrap">
          {imagePreviewUrls.map((url, index) => (
            <div key={index} className="relative group">
              <img
                src={url}
                alt={`Upload ${index + 1}`}
                className="w-16 h-16 object-cover rounded-lg border border-gray-200 dark:border-gray-700"
              />
              <button
                onClick={() => removeImage(index)}
                className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                aria-label="Remove image"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
      
      {/* Input area */}
      <div className="relative flex items-end gap-2 p-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl shadow-sm focus-within:ring-2 focus-within:ring-orange-500/20 transition-all">
        {/* Image upload button */}
        <button
          onClick={handleImageClick}
          disabled={images.length >= MAX_IMAGES || isStreaming}
          className={`
            p-2 rounded-lg transition-all duration-200
            ${images.length >= MAX_IMAGES || isStreaming
              ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
              : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-700 dark:hover:text-gray-300'
            }
          `}
          title={images.length >= MAX_IMAGES ? `Maximum ${MAX_IMAGES} images` : 'Attach file'}
          aria-label="Attach file"
        >
          <Paperclip className="w-5 h-5" />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept={SUPPORTED_FORMATS.join(',')}
          multiple
          onChange={handleFileChange}
          className="hidden"
        />

        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          onCompositionStart={() => setIsComposing(true)}
          onCompositionEnd={() => setIsComposing(false)}
          placeholder={images.length > 0 ? 'Describe your image or ask a question...' : placeholder}
          rows={1}
          className="flex-1 max-h-[200px] py-1.5 px-2 bg-transparent border-none focus:ring-0 focus:outline-none resize-none text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 text-sm leading-relaxed scrollbar-hide"
        />
        {isStreaming ? (
          <button
            onClick={handleCancel}
            className="p-2 rounded-lg transition-all duration-200 bg-red-500 text-white hover:bg-red-600 shadow-sm"
            title="Stop generating"
            aria-label="Stop generating"
          >
            <Square className="w-5 h-5" />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!canSend}
            className={`
              p-2 rounded-lg transition-all duration-200
              ${canSend
                ? 'bg-blue-500 text-white hover:bg-blue-600 shadow-sm'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed'
              }
            `}
            aria-label="Send message"
          >
            <SendHorizontal className="w-5 h-5" />
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Convert a File to base64 string
 */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
