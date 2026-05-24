import { useCallback, useEffect, useMemo, useState } from 'react';
import { BookOpen, CheckCircle2, ChevronDown, ChevronUp, Edit2, FileText, Loader2, Plus, RefreshCcw, Trash2, X } from 'lucide-react';
import { useAuth } from '../contexts';
import {
  createPersonalDocument,
  deletePersonalDocument,
  getKnowledgeMetadataOptions,
  listPersonalDocuments,
  updatePersonalDocument,
} from '../services/api';
import type { MetadataOptions, PersonalDocPayload, PersonalDocument } from '../types';

const INITIAL_FORM: PersonalDocPayload = {
  dish_name: '',
  category: '',
  difficulty: '',
  data_source: 'personal',
  content: '',
};

// Number of chips to show initially before expanding
const DISH_NAME_CHIP_COUNT = 12;
const DEFAULT_CHIP_COUNT = 7;

interface ChipSectionProps {
  values: string[];
  onSelect: (val: string) => void;
  initialCount?: number;
}

function ExpandableChips({ values, onSelect, initialCount = DEFAULT_CHIP_COUNT }: ChipSectionProps) {
  const [expanded, setExpanded] = useState(false);
  const displayValues = expanded ? values : values.slice(0, initialCount);
  const hasMore = values.length > initialCount;

  if (values.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 mt-2 items-center">
      {displayValues.map((val) => (
        <button
          key={val}
          type="button"
          onClick={() => onSelect(val)}
          className="text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700 transition-colors"
        >
          {val}
        </button>
      ))}
      {hasMore && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="text-xs px-2 py-1 rounded-full border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-1"
        >
          {expanded ? (
            <>
              <ChevronUp className="w-3 h-3" />
              收起
            </>
          ) : (
            <>
              <ChevronDown className="w-3 h-3" />
              展开 ({values.length - initialCount} 更多)
            </>
          )}
        </button>
      )}
    </div>
  );
}

export default function KnowledgePanel() {
  const { token } = useAuth();
  const [form, setForm] = useState<PersonalDocPayload>(INITIAL_FORM);
  const [options, setOptions] = useState<MetadataOptions>({ dish_name: [], category: [], difficulty: [] });
  const [documents, setDocuments] = useState<PersonalDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  // Edit mode state
  const [editingDocId, setEditingDocId] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const loadOptions = useCallback(async () => {
    if (!token) return;
    try {
      const result = await getKnowledgeMetadataOptions(token);
      setOptions(result);
    } catch (err) {
      console.error('Failed to load metadata options', err);
    }
  }, [token]);

  const loadDocuments = useCallback(async () => {
    if (!token) return;
    try {
      const res = await listPersonalDocuments(token);
      setDocuments(res.items || []);
    } catch (err) {
      console.error('Failed to load personal documents', err);
    }
  }, [token]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        await Promise.all([loadOptions(), loadDocuments()]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [loadDocuments, loadOptions]);

  const handleInput = (key: keyof PersonalDocPayload, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setError(null);
    setSuccess(null);
  };

  const isValid = useMemo(() => {
    return form.dish_name.trim() && form.category.trim() && form.difficulty.trim() && form.content.trim();
  }, [form]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) {
      setError('请先登录');
      return;
    }
    if (!isValid) {
      setError('请填写必填项');
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const payload = {
        ...form,
        dish_name: form.dish_name.trim(),
        category: form.category.trim(),
        difficulty: form.difficulty.trim(),
        content: form.content.trim(),
        data_source: 'personal' as const,
      };

      if (editingDocId) {
        // Update existing document
        const updated = await updatePersonalDocument(editingDocId, payload, token);
        setDocuments((prev) => prev.map((d) => (d.id === editingDocId ? updated : d)));
        setSuccess('文档已更新');
        setEditingDocId(null);
      } else {
        // Create new document
        const created = await createPersonalDocument(payload, token);
        setDocuments((prev) => [created, ...prev]);
        setSuccess('已保存到个人知识库并完成向量化');
      }
      setForm(INITIAL_FORM);
      await loadOptions();
    } catch (err: any) {
      setError(err?.message || '提交失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = (doc: PersonalDocument) => {
    setForm({
      dish_name: doc.dish_name,
      category: doc.category,
      difficulty: doc.difficulty,
      data_source: 'personal',
      content: doc.content,
    });
    setEditingDocId(doc.id);
    setError(null);
    setSuccess(null);
    // Scroll to form
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleCancelEdit = () => {
    setForm(INITIAL_FORM);
    setEditingDocId(null);
    setError(null);
    setSuccess(null);
  };

  const handleDelete = async (docId: string) => {
    if (!token) return;
    const deletedDoc = documents.find((d) => d.id === docId);
    setDeleting(true);
    try {
      await deletePersonalDocument(docId, token);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
      await Promise.all([loadDocuments(), loadOptions()]);
      setDeleteConfirmId(null);
      setSuccess(`已删除「${deletedDoc?.dish_name ?? '文档'}」`);
    } catch (err: any) {
      setError(err?.message || '删除失败');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex-1 overflow-auto p-4 md:p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="rounded-3xl border border-amber-100/70 dark:border-amber-900/40 bg-gradient-to-br from-orange-50 via-white to-amber-50 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800 p-6 shadow-sm">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
            <div className="flex items-center gap-3 text-amber-700 dark:text-amber-200">
              <div className="p-2 rounded-2xl bg-amber-100/70 dark:bg-amber-900/40">
                <BookOpen className="w-6 h-6" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">知识库</h1>
                <p className="text-sm text-amber-700/80 dark:text-amber-200/80 mt-1">
                  维护个人菜谱与技巧，让检索答案更贴合你的偏好
                </p>
              </div>
            </div>
            <button
              onClick={() => {
                loadDocuments();
                loadOptions();
              }}
              className="flex items-center gap-2 text-sm px-3 py-2 rounded-xl border border-amber-200/60 dark:border-amber-900/40 text-amber-700 dark:text-amber-200 hover:bg-amber-100/70 dark:hover:bg-amber-900/20 transition-colors"
            >
              <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              同步知识库
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Form Section */}
          <section className="lg:col-span-2 bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm p-4 md:p-5">
            <div className="flex items-center justify-between gap-2 mb-4">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 md:w-9 md:h-9 rounded-xl bg-orange-100 dark:bg-orange-500/10 flex items-center justify-center">
                  {editingDocId ? <Edit2 className="w-4 h-4 md:w-5 md:h-5 text-orange-500" /> : <Plus className="w-4 h-4 md:w-5 md:h-5 text-orange-500" />}
                </div>
                <div>
                  <h2 className="font-semibold text-base md:text-lg">{editingDocId ? '编辑文档' : '新增文档'}</h2>
                  <p className="text-xs text-gray-500">填写菜品元信息，正文支持完整 Markdown</p>
                </div>
              </div>
              {editingDocId && (
                <button
                  type="button"
                  onClick={handleCancelEdit}
                  className="text-xs px-2 py-1 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-1"
                >
                  <X className="w-3 h-3" />
                  取消编辑
                </button>
              )}
            </div>

            {error && (
              <div className="mb-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3 dark:bg-red-900/30 dark:text-red-200 dark:border-red-800">
                {error}
              </div>
            )}
            {success && (
              <div className="mb-3 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg p-3 dark:bg-emerald-900/30 dark:text-emerald-100 dark:border-emerald-800 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4" />
                {success}
              </div>
            )}

            <form className="space-y-4" onSubmit={handleSubmit}>
              {/* Dish name - full width row */}
              <div>
                <label className="text-sm font-medium">菜品名称 *</label>
                <input
                  list="dish-options"
                  value={form.dish_name}
                  onChange={(e) => handleInput('dish_name', e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-200 dark:border-gray-800 bg-transparent px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500"
                  placeholder="如：番茄炒蛋、宫保鸡丁"
                />
                <ExpandableChips values={options.dish_name} onSelect={(val) => handleInput('dish_name', val)} initialCount={DISH_NAME_CHIP_COUNT} />
              </div>

              {/* Category and Difficulty - same row */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium">菜品类别 *</label>
                  <input
                    list="category-options"
                    value={form.category}
                    onChange={(e) => handleInput('category', e.target.value)}
                    className="mt-1 w-full rounded-lg border border-gray-200 dark:border-gray-800 bg-transparent px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500"
                    placeholder="如：家常菜 / 汤品 / 技巧"
                  />
                  <ExpandableChips values={options.category} onSelect={(val) => handleInput('category', val)} />
                </div>
                <div>
                  <label className="text-sm font-medium">制作难度 *</label>
                  <input
                    list="difficulty-options"
                    value={form.difficulty}
                    onChange={(e) => handleInput('difficulty', e.target.value)}
                    className="mt-1 w-full rounded-lg border border-gray-200 dark:border-gray-800 bg-transparent px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500"
                    placeholder="如：简单 / 中等 / 困难"
                  />
                  <ExpandableChips values={options.difficulty} onSelect={(val) => handleInput('difficulty', val)} />
                </div>
              </div>

              <div>
                <label className="text-sm font-medium">Markdown 内容 *</label>
                <textarea
                  value={form.content}
                  onChange={(e) => handleInput('content', e.target.value)}
                  rows={8}
                  className="mt-1 w-full rounded-lg border border-gray-200 dark:border-gray-800 bg-transparent px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500 font-mono text-sm"
                  placeholder={"# 菜品名称\n\n## 原料\n- 原料1\n- 原料2\n\n## 步骤\n1. 第一步\n2. 第二步\n\n## 小技巧\n分享一些烹饪技巧..."}
                />
                <p className="text-xs text-gray-500 mt-1">支持完整 Markdown，提交后自动向量化并进入个人 RAG 库</p>
              </div>

              <div className="flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setForm(INITIAL_FORM);
                    setEditingDocId(null);
                  }}
                  className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 text-sm hover:bg-gray-100 dark:hover:bg-gray-800"
                >
                  重置
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 rounded-lg bg-orange-500 text-white text-sm font-semibold shadow hover:bg-orange-600 transition disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      正在提交...
                    </>
                  ) : editingDocId ? (
                    <>
                      <CheckCircle2 className="w-4 h-4" />
                      保存修改
                    </>
                  ) : (
                    <>
                      <Plus className="w-4 h-4" />
                      保存到知识库
                    </>
                  )}
                </button>
              </div>
            </form>
          </section>

          {/* Documents List Section */}
          <section className="bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm p-4 md:p-5">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-8 h-8 md:w-9 md:h-9 rounded-xl bg-amber-100 dark:bg-amber-500/10 flex items-center justify-center">
                <FileText className="w-4 h-4 md:w-5 md:h-5 text-amber-500" />
              </div>
              <div>
                <h2 className="font-semibold text-base md:text-lg">我的文档 ({documents.length})</h2>
                <p className="text-xs text-gray-500">提交成功即刻可检索</p>
              </div>
            </div>

            {loading ? (
              <div className="flex items-center justify-center h-32 text-sm text-gray-500">
                <Loader2 className="w-4 h-4 animate-spin mr-2" /> 加载中...
              </div>
            ) : documents.length === 0 ? (
              <div className="h-32 flex flex-col items-center justify-center text-sm text-gray-500">
                <BookOpen className="w-6 h-6 mb-2 text-gray-400" />
                <p>还没有个人文档，快去添加一篇吧</p>
              </div>
            ) : (
              <div className="space-y-3 max-h-[50vh] lg:max-h-[60vh] overflow-y-auto pr-1">
                {documents.map((doc) => (
                  <article
                    key={doc.id}
                    className={`p-3 rounded-xl border bg-gradient-to-r from-white to-gray-50 dark:from-gray-900 dark:to-gray-900/40 transition-colors ${
                      editingDocId === doc.id
                        ? 'border-orange-400 dark:border-orange-600'
                        : 'border-gray-200 dark:border-gray-800'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">{doc.dish_name}</p>
                        <p className="text-xs text-gray-500">{doc.category} · {doc.difficulty}</p>
                      </div>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => handleEdit(doc)}
                          className="p-1.5 rounded-lg text-gray-500 hover:text-amber-600 hover:bg-amber-50 dark:hover:text-amber-400 dark:hover:bg-amber-900/30 transition-colors"
                          title="编辑"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        {deleteConfirmId === doc.id ? (
                          <div className="flex items-center gap-1">
                            <button
                              type="button"
                              onClick={() => handleDelete(doc.id)}
                              disabled={deleting}
                              className="p-1.5 rounded-lg text-white bg-red-500 hover:bg-red-600 transition-colors disabled:opacity-50"
                              title="确认删除"
                            >
                              {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                            </button>
                            <button
                              type="button"
                              onClick={() => setDeleteConfirmId(null)}
                              className="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                              title="取消"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setDeleteConfirmId(doc.id)}
                            className="p-1.5 rounded-lg text-gray-500 hover:text-red-600 hover:bg-red-50 dark:hover:text-red-400 dark:hover:bg-red-900/30 transition-colors"
                            title="删除"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                    <p className="text-xs text-gray-500 mt-2 whitespace-pre-wrap overflow-hidden max-h-16 line-clamp-3">
                      {doc.content.slice(0, 150)}{doc.content.length > 150 ? '…' : ''}
                    </p>
                    <div className="text-[11px] text-gray-400 mt-2">更新于 {new Date(doc.updated_at).toLocaleString()}</div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
