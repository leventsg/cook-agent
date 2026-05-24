/**
 * User Profile Modal
 * Settings dialog for user profile and appearance
 */

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Settings, Palette, Plug, Bot, Trash2, Pencil } from 'lucide-react';
import {
  createMcpServer,
  deleteMcpServer,
  getProfile,
  listMcpServers,
  updateMcpServer,
  updateProfile,
  createSubagent,
  deleteSubagent,
  updateSubagent,
  listSubagents,
  getAvailableTools,
} from '../../services/api';
import { useAuth, useTheme } from '../../contexts';
import type { SubagentSchema, ToolSchema } from '../../types';

export interface UserProfileModalProps {
  open: boolean;
  onClose: () => void;
}

export function UserProfileModal({ open, onClose }: UserProfileModalProps) {
  const { token, updateProfile: ctxUpdate } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const [username, setUsername] = useState('');
  const [occupation, setOccupation] = useState('');
  const [bio, setBio] = useState('');
  const [profile, setProfile] = useState('');
  const [userInstruction, setUserInstruction] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | string[] | null>(null);
  const [activeTab, setActiveTab] = useState<'general' | 'appearance' | 'mcp' | 'agents'>('general');
  const [mcpServers, setMcpServers] = useState<{
    name: string;
    endpoint: string;
    authHeaderName?: string | null;
    authToken?: string | null;
  }[]>([]);
  const [mcpName, setMcpName] = useState('');
  const [mcpEndpoint, setMcpEndpoint] = useState('');
  const [mcpAuthHeaderName, setMcpAuthHeaderName] = useState('Authorization');
  const [mcpAuthToken, setMcpAuthToken] = useState('');
  const [mcpAuthEnabled, setMcpAuthEnabled] = useState(false);
  const [mcpLoading, setMcpLoading] = useState(false);
  const [editingMcpName, setEditingMcpName] = useState<string | null>(null);
  const [subagents, setSubagents] = useState<SubagentSchema[]>([]);
  const [availableAgentTools, setAvailableAgentTools] = useState<ToolSchema[]>([]);
  const [agentName, setAgentName] = useState('');
  const [agentDisplayName, setAgentDisplayName] = useState('');
  const [agentDescription, setAgentDescription] = useState('');
  const [agentSystemPrompt, setAgentSystemPrompt] = useState('');
  const [agentTools, setAgentTools] = useState<string[]>([]);
  const [agentMaxIterations, setAgentMaxIterations] = useState(10);
  const [agentLoading, setAgentLoading] = useState(false);
  const [editingAgentName, setEditingAgentName] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !token) return;
    let cancelled = false;
    setLoading(true);
    getProfile(token)
      .then((res) => {
        if (cancelled) return;
        setUsername(res.username || '');
        setOccupation(res.occupation || '');
        setBio(res.bio || '');
        setProfile(res.profile || '');
        setUserInstruction(res.user_instruction || '');
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));

    listMcpServers(token)
      .then((res) => {
        if (cancelled) return;
        setMcpServers(
          res.servers.map((server) => ({
            name: server.name,
            endpoint: server.endpoint,
            authHeaderName: server.auth_header_name ?? null,
            authToken: server.auth_token ?? null,
          }))
        );
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));

    listSubagents(token)
      .then((res) => {
        if (cancelled) return;
        setSubagents(res.subagents);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));

    getAvailableTools(token)
      .then((res) => {
        if (cancelled) return;
        const toolMap = new Map<string, ToolSchema>();
        res.servers.forEach((server) => {
          server.tools.forEach((tool) => {
            if (!tool.name.startsWith('subagent_')) {
              toolMap.set(tool.name, tool);
            }
          });
        });
        setAvailableAgentTools(Array.from(toolMap.values()));
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [open, token]);

  const handleSave = async () => {
    setError(null);
    if (!token) return setError('Not authenticated');
    setLoading(true);
    try {
      const res = await updateProfile({ username, occupation, bio, profile, user_instruction: userInstruction }, token);
      if (ctxUpdate) {
        await ctxUpdate({
          username: res.username,
          occupation: res.occupation ?? undefined,
          bio: res.bio ?? undefined,
        });
      }
      onClose();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(
        msg.includes('\n')
          ? msg
              .split('\n')
              .map((s) => s.trim())
              .filter(Boolean)
          : msg
      );
    } finally {
      setLoading(false);
    }
  };

  const resetMcpForm = () => {
    setMcpName('');
    setMcpEndpoint('');
    setMcpAuthEnabled(false);
    setMcpAuthHeaderName('Authorization');
    setMcpAuthToken('');
    setEditingMcpName(null);
  };

  const handleAddMcpServer = async () => {
    setError(null);
    if (!token) return setError('Not authenticated');
    if (!mcpName.trim() || !mcpEndpoint.trim()) {
      return setError('请填写 MCP 名称和 Endpoint');
    }
    setMcpLoading(true);
    try {
      const server = await createMcpServer(
        {
          name: mcpName.trim(),
          endpoint: mcpEndpoint.trim(),
          auth_header_name: mcpAuthEnabled ? mcpAuthHeaderName.trim() : null,
          auth_token: mcpAuthEnabled ? mcpAuthToken.trim() : null,
        },
        token
      );
      setMcpServers((prev) => [
        {
          name: server.name,
          endpoint: server.endpoint,
          authHeaderName: server.auth_header_name ?? null,
          authToken: server.auth_token ?? null,
        },
        ...prev,
      ]);
      setMcpName('');
      setMcpEndpoint('');
      setMcpAuthEnabled(false);
      setMcpAuthHeaderName('Authorization');
      setMcpAuthToken('');
      setEditingMcpName(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(
        msg.includes('\n')
          ? msg
              .split('\n')
              .map((s) => s.trim())
              .filter(Boolean)
          : msg
      );
    } finally {
      setMcpLoading(false);
    }
  };

  const handleEditMcpServer = (server: {
    name: string;
    endpoint: string;
    authHeaderName?: string | null;
    authToken?: string | null;
  }) => {
    setEditingMcpName(server.name);
    setMcpName(server.name);
    setMcpEndpoint(server.endpoint);
    const hasAuth = !!(server.authHeaderName && server.authToken);
    setMcpAuthEnabled(hasAuth);
    setMcpAuthHeaderName(server.authHeaderName ?? 'Authorization');
    setMcpAuthToken(server.authToken ?? '');
  };

  const handleUpdateMcpServer = async () => {
    setError(null);
    if (!token) return setError('Not authenticated');
    if (!editingMcpName) return;
    if (!mcpEndpoint.trim()) {
      return setError('请填写 MCP Endpoint');
    }
    if (mcpAuthEnabled && !mcpAuthToken.trim()) {
      return setError('请填写认证 Token');
    }

    setMcpLoading(true);
    try {
      const updated = await updateMcpServer(
        editingMcpName,
        {
          endpoint: mcpEndpoint.trim(),
          auth_header_name: mcpAuthEnabled ? mcpAuthHeaderName.trim() : null,
          auth_token: mcpAuthEnabled ? mcpAuthToken.trim() : null,
        },
        token
      );
      setMcpServers((prev) =>
        prev.map((server) =>
          server.name === editingMcpName
            ? {
                name: updated.name,
                endpoint: updated.endpoint,
                authHeaderName: updated.auth_header_name ?? null,
                authToken: updated.auth_token ?? null,
              }
            : server
        )
      );
      resetMcpForm();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(
        msg.includes('\n')
          ? msg
              .split('\n')
              .map((s) => s.trim())
              .filter(Boolean)
          : msg
      );
    } finally {
      setMcpLoading(false);
    }
  };

  const handleDeleteMcpServer = async (name: string) => {
    setError(null);
    if (!token) return setError('Not authenticated');
    if (!window.confirm(`确认删除 MCP 服务器 ${name} 吗？`)) return;

    setMcpLoading(true);
    try {
      await deleteMcpServer(name, token);
      setMcpServers((prev) => prev.filter((server) => server.name !== name));
      if (editingMcpName === name) {
        resetMcpForm();
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(
        msg.includes('\n')
          ? msg
              .split('\n')
              .map((s) => s.trim())
              .filter(Boolean)
          : msg
      );
    } finally {
      setMcpLoading(false);
    }
  };

  const resetAgentForm = () => {
    setAgentName('');
    setAgentDisplayName('');
    setAgentDescription('');
    setAgentSystemPrompt('');
    setAgentTools([]);
    setAgentMaxIterations(10);
    setEditingAgentName(null);
  };

  const handleAddSubagent = async () => {
    setError(null);
    if (!token) return setError('Not authenticated');
    if (!agentName.trim() || !agentDisplayName.trim()) {
      return setError('请填写 Agent 名称和显示名称');
    }
    if (!agentDescription.trim() || !agentSystemPrompt.trim()) {
      return setError('请填写 Agent 描述和系统提示词');
    }

    setAgentLoading(true);
    try {
      const created = await createSubagent(
        {
          name: agentName.trim(),
          display_name: agentDisplayName.trim(),
          description: agentDescription.trim(),
          system_prompt: agentSystemPrompt.trim(),
          tools: agentTools,
          max_iterations: agentMaxIterations,
          category: 'custom',
        },
        token
      );

      setSubagents((prev) => [created, ...prev]);
      setAgentName('');
      setAgentDisplayName('');
      setAgentDescription('');
      setAgentSystemPrompt('');
      setAgentTools([]);
      setAgentMaxIterations(10);
      setEditingAgentName(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(
        msg.includes('\n')
          ? msg
              .split('\n')
              .map((s) => s.trim())
              .filter(Boolean)
          : msg
      );
    } finally {
      setAgentLoading(false);
    }
  };

  const handleEditSubagent = (agent: SubagentSchema) => {
    setEditingAgentName(agent.name);
    setAgentName(agent.name);
    setAgentDisplayName(agent.display_name);
    setAgentDescription(agent.description);
    setAgentSystemPrompt(agent.system_prompt ?? '');
    setAgentTools(agent.tools);
    setAgentMaxIterations(agent.max_iterations);
  };

  const handleUpdateSubagent = async () => {
    setError(null);
    if (!token) return setError('Not authenticated');
    if (!editingAgentName) return;
    if (!agentDisplayName.trim()) {
      return setError('请填写 Agent 显示名称');
    }
    if (!agentDescription.trim() || !agentSystemPrompt.trim()) {
      return setError('请填写 Agent 描述和系统提示词');
    }

    setAgentLoading(true);
    try {
      const updated = await updateSubagent(
        editingAgentName,
        {
          display_name: agentDisplayName.trim(),
          description: agentDescription.trim(),
          system_prompt: agentSystemPrompt.trim(),
          tools: agentTools,
          max_iterations: agentMaxIterations,
          category: 'custom',
        },
        token
      );
      setSubagents((prev) =>
        prev.map((agent) => (agent.name === updated.name ? updated : agent))
      );
      resetAgentForm();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(
        msg.includes('\n')
          ? msg
              .split('\n')
              .map((s) => s.trim())
              .filter(Boolean)
          : msg
      );
    } finally {
      setAgentLoading(false);
    }
  };

  const handleDeleteSubagent = async (name: string) => {
    setError(null);
    if (!token) return setError('Not authenticated');
    setAgentLoading(true);
    try {
      await deleteSubagent(name, token);
      setSubagents((prev) => prev.filter((agent) => agent.name !== name));
      if (editingAgentName === name) {
        resetAgentForm();
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(
        msg.includes('\n')
          ? msg
              .split('\n')
              .map((s) => s.trim())
              .filter(Boolean)
          : msg
      );
    } finally {
      setAgentLoading(false);
    }
  };

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4 py-8">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="relative w-full max-w-4xl bg-white dark:bg-[#0f172a] rounded-2xl shadow-2xl border border-gray-200/70 dark:border-gray-800/70 overflow-hidden flex flex-col h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200/80 dark:border-gray-800/80 shrink-0 bg-gradient-to-r from-white to-gray-50 dark:from-[#0f172a] dark:to-gray-900/50">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-400 to-orange-500 flex items-center justify-center shadow-lg shadow-orange-500/30">
              <Settings className="w-4 h-4 text-white" />
            </div>
            <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-50">
              设置
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200 transition-all duration-200"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Left Sidebar */}
          <div className="w-60 border-r border-gray-200/80 dark:border-gray-800/80 bg-gray-50/80 dark:bg-gray-900/30 p-4 flex flex-col gap-2 shrink-0">
            <TabButton
              active={activeTab === 'general'}
              onClick={() => setActiveTab('general')}
              icon={<Settings size={18} />}
              label="常规设置"
            />
            <TabButton
              active={activeTab === 'appearance'}
              onClick={() => setActiveTab('appearance')}
              icon={<Palette size={18} />}
              label="个性化"
            />
            <TabButton
              active={activeTab === 'mcp'}
              onClick={() => setActiveTab('mcp')}
              icon={<Plug size={18} />}
              label="MCP 配置"
            />
            <TabButton
              active={activeTab === 'agents'}
              onClick={() => setActiveTab('agents')}
              icon={<Bot size={18} />}
              label="Agent 配置"
            />
          </div>

          {/* Right Content */}
          <div className="flex-1 p-6 bg-gradient-to-b from-white/60 via-white to-white/60 dark:from-gray-900/40 dark:via-gray-900/70 dark:to-gray-900/40 flex flex-col">
            {/* Error Display */}
            {error && (
              <div className="mb-4 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">
                {Array.isArray(error) ? (
                  <ul className="list-disc ml-5 space-y-1">
                    {error.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                ) : (
                  <div>{error}</div>
                )}
              </div>
            )}

            {activeTab === 'general' && (
              <GeneralTab
                username={username}
                occupation={occupation}
                bio={bio}
                loading={loading}
                onUsernameChange={setUsername}
                onOccupationChange={setOccupation}
                onBioChange={setBio}
                onSave={handleSave}
              />
            )}

            {activeTab === 'appearance' && (
              <AppearanceTab
                isDark={isDark}
                toggleTheme={toggleTheme}
                profile={profile}
                userInstruction={userInstruction}
                loading={loading}
                onProfileChange={setProfile}
                onUserInstructionChange={setUserInstruction}
                onSave={handleSave}
              />
            )}

            {activeTab === 'mcp' && (
              <McpTab
                name={mcpName}
                endpoint={mcpEndpoint}
                servers={mcpServers}
                loading={mcpLoading}
                editingName={editingMcpName}
                authHeaderName={mcpAuthHeaderName}
                authToken={mcpAuthToken}
                authEnabled={mcpAuthEnabled}
                onNameChange={setMcpName}
                onEndpointChange={setMcpEndpoint}
                onAuthHeaderNameChange={setMcpAuthHeaderName}
                onAuthTokenChange={setMcpAuthToken}
                onAuthEnabledChange={setMcpAuthEnabled}
                onAdd={handleAddMcpServer}
                onUpdate={handleUpdateMcpServer}
                onCancelEdit={resetMcpForm}
                onEdit={handleEditMcpServer}
                onDelete={handleDeleteMcpServer}
              />
            )}

            {activeTab === 'agents' && (
              <AgentTab
                name={agentName}
                displayName={agentDisplayName}
                description={agentDescription}
                systemPrompt={agentSystemPrompt}
                tools={agentTools}
                maxIterations={agentMaxIterations}
                availableTools={availableAgentTools}
                subagents={subagents}
                loading={agentLoading}
                editingName={editingAgentName}
                onNameChange={setAgentName}
                onDisplayNameChange={setAgentDisplayName}
                onDescriptionChange={setAgentDescription}
                onSystemPromptChange={setAgentSystemPrompt}
                onToolsChange={setAgentTools}
                onMaxIterationsChange={setAgentMaxIterations}
                onAdd={handleAddSubagent}
                onUpdate={handleUpdateSubagent}
                onCancelEdit={resetAgentForm}
                onEdit={handleEditSubagent}
                onDelete={handleDeleteSubagent}
              />
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

/**
 * Tab button in sidebar
 */
function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200 ${
        active
          ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-md shadow-gray-200/50 dark:shadow-gray-900/50 border border-gray-200/60 dark:border-gray-700/60'
          : 'text-gray-600 dark:text-gray-400 hover:bg-white/60 dark:hover:bg-gray-800/50 hover:text-gray-900 dark:hover:text-gray-200'
      }`}
    >
      <div
        className={`p-1.5 rounded-lg ${
          active ? 'bg-orange-100 dark:bg-orange-900/40 text-orange-600 dark:text-orange-400' : 'bg-transparent'
        }`}
      >
        {icon}
      </div>
      {label}
    </button>
  );
}

/**
 * General settings tab
 */
function GeneralTab({
  username,
  occupation,
  bio,
  loading,
  onUsernameChange,
  onOccupationChange,
  onBioChange,
  onSave,
}: {
  username: string;
  occupation: string;
  bio: string;
  loading: boolean;
  onUsernameChange: (value: string) => void;
  onOccupationChange: (value: string) => void;
  onBioChange: (value: string) => void;
  onSave: () => void;
}) {
  return (
    <>
      <div className="flex-1 overflow-y-auto pr-1">
        <div className="mb-6">
          <p className="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500 mb-2">
            基本信息
          </p>
          <h4 className="text-2xl font-semibold text-gray-900 dark:text-gray-50">
            个人资料
          </h4>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            更新您的用户名、职业与简介，让更多人了解您。
          </p>
        </div>

        <div className="space-y-5">
          <FormField label="用户名">
            <input
              value={username}
              onChange={(e) => onUsernameChange(e.target.value)}
              className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-4 py-2.5 focus:outline-none focus:border-orange-400 dark:focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 transition-all duration-200"
            />
          </FormField>

          <FormField label="职业">
            <input
              value={occupation}
              onChange={(e) => onOccupationChange(e.target.value)}
              className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-4 py-2.5 focus:outline-none focus:border-orange-400 dark:focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 transition-all duration-200"
            />
          </FormField>

          <FormField label="简介">
            <textarea
              value={bio}
              onChange={(e) => onBioChange(e.target.value)}
              rows={4}
              className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-4 py-2.5 resize-none focus:outline-none focus:border-orange-400 dark:focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 transition-all duration-200"
            />
          </FormField>
        </div>
      </div>

      <div className="pt-4 flex justify-end shrink-0 border-t border-gray-200/60 dark:border-gray-800/60">
        <button
          onClick={onSave}
          disabled={loading}
          className="px-6 py-2.5 rounded-lg bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 text-white font-medium disabled:opacity-70 shadow-lg shadow-orange-500/30 hover:shadow-orange-500/40 transition-all duration-200 hover:-translate-y-0.5"
        >
          {loading ? '保存中...' : '保存更改'}
        </button>
      </div>
    </>
  );
}

/**
 * Form field wrapper
 */
function FormField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium text-gray-700 dark:text-gray-200">
        {label}
      </label>
      {children}
    </div>
  );
}

/**
 * Appearance settings tab
 */
function AppearanceTab({
  isDark,
  toggleTheme,
  profile,
  userInstruction,
  loading,
  onProfileChange,
  onUserInstructionChange,
  onSave,
}: {
  isDark: boolean;
  toggleTheme: () => void;
  profile: string;
  userInstruction: string;
  loading: boolean;
  onProfileChange: (value: string) => void;
  onUserInstructionChange: (value: string) => void;
  onSave: () => void;
}) {
  return (
    <>
      <div className="flex-1 overflow-y-auto pr-1">

        <div className="mb-6">
          <p className="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500 mb-2">
            外观设置
          </p>
          <h4 className="text-2xl font-semibold text-gray-900 dark:text-gray-50">
            个性化
          </h4>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            自定义您的使用偏好和 AI 助手交互方式。
          </p>
        </div>

        <div className="p-5 rounded-xl bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-800/50 dark:to-gray-900/50 border border-gray-200/60 dark:border-gray-700/60 mb-6">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}>
                {isDark ? (
                  <svg className="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5 text-gray-600" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
                  </svg>
                )}
              </div>
              <div>
                <div className="text-sm font-medium text-gray-800 dark:text-gray-100">
                  主题模式
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  当前：{isDark ? '深色模式 🌙' : '浅色模式 ☀️'}
                </div>
              </div>
            </div>
            <button
              onClick={toggleTheme}
              className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-100 hover:bg-gray-50 dark:hover:bg-gray-600 transition-all duration-200 text-sm font-medium shadow-sm hover:shadow"
            >
              切换主题
            </button>
          </div>
        </div>

        {/* AI 个性化设置 */}
        <div className="pt-2">
          <div className="mb-4">
            <h4 className="text-lg font-semibold text-gray-900 dark:text-gray-50">
              AI 助手个性化
            </h4>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              配置 AI 助手对您的了解和回答风格偏好，这些设置将在所有对话中自动生效。
            </p>
          </div>

          <div className="space-y-5">
            <FormField label="个人信息 (Profile)">
              <textarea
                value={profile}
                onChange={(e) => onProfileChange(e.target.value)}
                rows={4}
                placeholder="描述你的背景、偏好、饮食习惯等，例如：我是素食主义者，偏好清淡口味，家里有两个孩子..."
                className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-4 py-2.5 resize-none focus:outline-none focus:border-orange-400 dark:focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 transition-all duration-200"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 flex items-center gap-1">
                <span className="w-1 h-1 rounded-full bg-gray-400"></span>
                用于描述你的基本背景、身份、饮食偏好等个人特征
              </p>
            </FormField>

            <FormField label="自定义指令 (User Instruction)">
              <textarea
                value={userInstruction}
                onChange={(e) => onUserInstructionChange(e.target.value)}
                rows={5}
                placeholder="定义你希望 AI 遵循的回答风格和规则，例如：请用简洁的语言回答，多使用emoji，优先推荐30分钟内能完成的快手菜..."
                className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-4 py-2.5 resize-none focus:outline-none focus:border-orange-400 dark:focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 transition-all duration-200"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 flex items-center gap-1">
                <span className="w-1 h-1 rounded-full bg-gray-400"></span>
                定义 AI 的回答风格、输出格式、关注重点等长期偏好
              </p>
            </FormField>
          </div>
        </div>
      </div>

      <div className="pt-4 flex justify-end shrink-0 border-t border-gray-200/60 dark:border-gray-800/60">
        <button
          onClick={onSave}
          disabled={loading}
          className="px-6 py-2.5 rounded-lg bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 text-white font-medium disabled:opacity-70 shadow-lg shadow-orange-500/30 hover:shadow-orange-500/40 transition-all duration-200 hover:-translate-y-0.5"
        >
          {loading ? '保存中...' : '保存更改'}
        </button>
      </div>
    </>
  );
}

function McpTab({
  name,
  endpoint,
  servers,
  loading,
  editingName,
  authHeaderName,
  authToken,
  authEnabled,
  onNameChange,
  onEndpointChange,
  onAuthHeaderNameChange,
  onAuthTokenChange,
  onAuthEnabledChange,
  onAdd,
  onUpdate,
  onCancelEdit,
  onEdit,
  onDelete,
}: {
  name: string;
  endpoint: string;
  servers: {
    name: string;
    endpoint: string;
    authHeaderName?: string | null;
    authToken?: string | null;
  }[];
  loading: boolean;
  editingName: string | null;
  authHeaderName: string;
  authToken: string;
  authEnabled: boolean;
  onNameChange: (value: string) => void;
  onEndpointChange: (value: string) => void;
  onAuthHeaderNameChange: (value: string) => void;
  onAuthTokenChange: (value: string) => void;
  onAuthEnabledChange: (value: boolean) => void;
  onAdd: () => void;
  onUpdate: () => void;
  onCancelEdit: () => void;
  onEdit: (server: {
    name: string;
    endpoint: string;
    authHeaderName?: string | null;
    authToken?: string | null;
  }) => void;
  onDelete: (name: string) => void;
}) {
  const isEditing = Boolean(editingName);

  return (
    <>
      <div className="flex-1 overflow-y-auto pr-1">
        <div className="mb-6">
          <p className="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500 mb-2">
            高级配置
          </p>
          <h4 className="text-2xl font-semibold text-gray-900 dark:text-gray-50">
            MCP 配置
          </h4>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            添加 StreamableHTTP 方式的 MCP 服务器，保存后将立即生效。
          </p>
        </div>

        <div className="p-5 rounded-xl bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-indigo-900/20 dark:to-purple-900/20 border border-indigo-200/60 dark:border-indigo-800/60 mb-6">
          <div className="space-y-4">
            <FormField label="MCP 名称">
              <input
                value={name}
                onChange={(e) => onNameChange(e.target.value)}
                placeholder="例如：amap"
                disabled={isEditing}
                className="w-full rounded-lg border border-indigo-200 dark:border-indigo-800 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-4 py-2.5 focus:outline-none focus:border-indigo-400 dark:focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all duration-200 disabled:opacity-70"
              />
            </FormField>

            <FormField label="Endpoint (StreamableHTTP)">
              <input
                value={endpoint}
                onChange={(e) => onEndpointChange(e.target.value)}
                placeholder="https://example.com/mcp"
                className="w-full rounded-lg border border-indigo-200 dark:border-indigo-800 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-4 py-2.5 focus:outline-none focus:border-indigo-400 dark:focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all duration-200"
              />
              <p className="text-xs text-indigo-600/70 dark:text-indigo-400/70 mt-1.5 flex items-center gap-1">
                <span className="w-1 h-1 rounded-full bg-indigo-400"></span>
                当前仅支持 StreamableHTTP，可选自定义认证 Header
              </p>
            </FormField>

            <div className="flex items-center gap-3 text-sm text-gray-700 dark:text-gray-300 p-3 rounded-lg bg-white/60 dark:bg-gray-800/60 border border-indigo-100 dark:border-indigo-800/40">
              <input
                type="checkbox"
                checked={authEnabled}
                onChange={(e) => onAuthEnabledChange(e.target.checked)}
                className="h-4 w-4 rounded border-indigo-300 dark:border-indigo-600 text-indigo-600 dark:text-indigo-400 focus:ring-indigo-500/40"
              />
              <span className="font-medium">启用认证 Header</span>
            </div>

            {authEnabled && (
              <div className="pl-4 border-l-2 border-indigo-200 dark:border-indigo-700 space-y-4 animate-in slide-in-from-top-2 duration-200">
                <FormField label="Header 名称">
                  <input
                    value={authHeaderName}
                    onChange={(e) => onAuthHeaderNameChange(e.target.value)}
                    placeholder="Authorization"
                    className="w-full rounded-lg border border-indigo-200 dark:border-indigo-800 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-4 py-2.5 focus:outline-none focus:border-indigo-400 dark:focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all duration-200"
                  />
                </FormField>

                <FormField label="Token">
                  <input
                    value={authToken}
                    onChange={(e) => onAuthTokenChange(e.target.value)}
                    placeholder="Bearer ..."
                    className="w-full rounded-lg border border-indigo-200 dark:border-indigo-800 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-4 py-2.5 focus:outline-none focus:border-indigo-400 dark:focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all duration-200"
                  />
                </FormField>
              </div>
            )}
          </div>

          <div className="mt-5 pt-4 border-t border-indigo-200/60 dark:border-indigo-700/60">
            <div className="flex items-center gap-3">
              <button
                onClick={isEditing ? onUpdate : onAdd}
                disabled={loading}
                className="flex-1 px-4 py-2.5 rounded-lg bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-medium disabled:opacity-70 shadow-lg shadow-indigo-500/30 hover:shadow-indigo-500/40 transition-all duration-200 hover:-translate-y-0.5"
              >
                {loading ? '保存中...' : isEditing ? '更新 MCP 服务器' : '添加 MCP 服务器'}
              </button>
              {isEditing && (
                <button
                  type="button"
                  onClick={onCancelEdit}
                  className="px-4 py-2.5 rounded-lg border border-indigo-200 dark:border-indigo-700 text-indigo-600 dark:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 transition-all duration-200"
                >
                  取消编辑
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="pt-2">
          <div className="flex items-center gap-2 mb-4">
            <div className="text-sm font-semibold text-gray-800 dark:text-gray-100">
              已添加的 MCP 服务器
            </div>
            <div className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
              {servers.length}
            </div>
          </div>
          <div className="space-y-2">
            {servers.length === 0 ? (
              <div className="p-4 rounded-lg border border-dashed border-gray-200 dark:border-gray-700 text-sm text-gray-500 dark:text-gray-400 text-center">
                暂无自定义 MCP 服务器
              </div>
            ) : (
              servers.map((server) => (
                <div
                  key={server.name}
                  className="flex items-center justify-between gap-3 rounded-lg border border-gray-200/60 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 px-4 py-3 hover:shadow-md hover:border-indigo-300/60 dark:hover:border-indigo-700/60 transition-all duration-200"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-100 to-purple-100 dark:from-indigo-900/40 dark:to-purple-900/40 flex items-center justify-center">
                      <Plug className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                    </div>
                    <div>
                      <div className="text-sm font-medium text-gray-800 dark:text-gray-100">
                        {server.name}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400 font-mono truncate max-w-[200px]">
                        {server.endpoint}
                      </div>
                      {server.authHeaderName && server.authToken && (
                        <div className="text-xs text-indigo-500 dark:text-indigo-400 flex items-center gap-1 mt-0.5">
                          <span className="w-1 h-1 rounded-full bg-indigo-400"></span>
                          Header: {server.authHeaderName}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2 py-1 rounded-full bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400 font-medium">
                      已启用
                    </span>
                    <button
                      type="button"
                      onClick={() => onEdit(server)}
                      className="p-2 rounded-lg text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 transition-all duration-200"
                      aria-label={`Edit ${server.name}`}
                    >
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(server.name)}
                      className="p-2 rounded-lg text-gray-500 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 transition-all duration-200"
                      aria-label={`Delete ${server.name}`}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function AgentTab({
  name,
  displayName,
  description,
  systemPrompt,
  tools,
  maxIterations,
  availableTools,
  subagents,
  loading,
  editingName,
  onNameChange,
  onDisplayNameChange,
  onDescriptionChange,
  onSystemPromptChange,
  onToolsChange,
  onMaxIterationsChange,
  onAdd,
  onUpdate,
  onCancelEdit,
  onEdit,
  onDelete,
}: {
  name: string;
  displayName: string;
  description: string;
  systemPrompt: string;
  tools: string[];
  maxIterations: number;
  availableTools: ToolSchema[];
  subagents: SubagentSchema[];
  loading: boolean;
  editingName: string | null;
  onNameChange: (value: string) => void;
  onDisplayNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onSystemPromptChange: (value: string) => void;
  onToolsChange: (value: string[]) => void;
  onMaxIterationsChange: (value: number) => void;
  onAdd: () => void;
  onUpdate: () => void;
  onCancelEdit: () => void;
  onEdit: (agent: SubagentSchema) => void;
  onDelete: (name: string) => void;
}) {
  const customAgents = subagents.filter((agent) => !agent.builtin);
  const isEditing = Boolean(editingName);

  return (
    <>
      <div className="flex-1 overflow-y-auto pr-1">
        <div className="mb-6">
          <p className="text-xs uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500 mb-2">
            高级配置
          </p>
          <h4 className="text-2xl font-semibold text-gray-900 dark:text-gray-50">
            Agent 配置
          </h4>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            创建自定义 Agent，并指定可用工具与执行策略。
          </p>
        </div>

        <div className="p-5 rounded-xl bg-gradient-to-br from-purple-50 to-indigo-50 dark:from-purple-900/20 dark:to-indigo-900/20 border border-purple-200/60 dark:border-purple-800/60 mb-6">
          <div className="space-y-4">
            <FormField label="Agent 名称">
              <input
                value={name}
                onChange={(e) => onNameChange(e.target.value)}
                placeholder="例如：recipe_helper"
                disabled={isEditing}
                className="w-full rounded-lg border border-purple-200 dark:border-purple-800 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-4 py-2.5 focus:outline-none focus:border-purple-400 dark:focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 transition-all duration-200 disabled:opacity-70"
              />
            </FormField>

            <FormField label="显示名称">
              <input
                value={displayName}
                onChange={(e) => onDisplayNameChange(e.target.value)}
                placeholder="例如：食谱助手"
                className="w-full rounded-lg border border-purple-200 dark:border-purple-800 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-4 py-2.5 focus:outline-none focus:border-purple-400 dark:focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 transition-all duration-200"
              />
            </FormField>

            <FormField label="描述">
              <textarea
                value={description}
                onChange={(e) => onDescriptionChange(e.target.value)}
                rows={3}
                placeholder="简要描述 Agent 的能力与擅长任务"
                className="w-full rounded-lg border border-purple-200 dark:border-purple-800 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-4 py-2.5 resize-none focus:outline-none focus:border-purple-400 dark:focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 transition-all duration-200"
              />
            </FormField>

            <FormField label="系统提示词">
              <textarea
                value={systemPrompt}
                onChange={(e) => onSystemPromptChange(e.target.value)}
                rows={4}
                placeholder="定义该 Agent 的角色、语气、工作流程等"
                className="w-full rounded-lg border border-purple-200 dark:border-purple-800 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 px-4 py-2.5 resize-none focus:outline-none focus:border-purple-400 dark:focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 transition-all duration-200"
              />
            </FormField>

            <FormField label="最大迭代次数">
              <input
                type="number"
                min={1}
                max={50}
                value={maxIterations}
                onChange={(e) => {
                  const next = Number(e.target.value);
                  const normalized = Number.isFinite(next)
                    ? Math.min(Math.max(next, 1), 50)
                    : 1;
                  onMaxIterationsChange(normalized);
                }}
                className="w-full rounded-lg border border-purple-200 dark:border-purple-800 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 px-4 py-2.5 focus:outline-none focus:border-purple-400 dark:focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 transition-all duration-200"
              />
            </FormField>

            <FormField label="可用工具">
              <div className="flex flex-wrap gap-2">
                {availableTools.length === 0 ? (
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    暂无可用工具
                  </span>
                ) : (
                  availableTools.map((tool) => {
                    const isSelected = tools.includes(tool.name);
                    return (
                      <label
                        key={tool.name}
                        className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs border transition-all duration-150 cursor-pointer ${
                          isSelected
                            ? 'bg-purple-500 text-white border-purple-500'
                            : 'bg-white/70 dark:bg-gray-800/60 text-gray-700 dark:text-gray-300 border-purple-200 dark:border-purple-800 hover:border-purple-400 dark:hover:border-purple-600'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => {
                            if (isSelected) {
                              onToolsChange(tools.filter((name) => name !== tool.name));
                            } else {
                              onToolsChange([...tools, tool.name]);
                            }
                          }}
                          className="hidden"
                        />
                        <span>{tool.name}</span>
                      </label>
                    );
                  })
                )}
              </div>
            </FormField>
          </div>

          <div className="mt-5 pt-4 border-t border-purple-200/60 dark:border-purple-700/60">
            <div className="flex items-center gap-3">
              <button
                onClick={isEditing ? onUpdate : onAdd}
                disabled={loading}
                className="flex-1 px-4 py-2.5 rounded-lg bg-gradient-to-r from-purple-500 to-indigo-600 hover:from-purple-600 hover:to-indigo-700 text-white font-medium disabled:opacity-70 shadow-lg shadow-purple-500/30 hover:shadow-purple-500/40 transition-all duration-200 hover:-translate-y-0.5"
              >
                {loading ? '保存中...' : isEditing ? '更新 Agent' : '添加 Agent'}
              </button>
              {isEditing && (
                <button
                  type="button"
                  onClick={onCancelEdit}
                  className="px-4 py-2.5 rounded-lg border border-purple-200 dark:border-purple-700 text-purple-600 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-900/30 transition-all duration-200"
                >
                  取消编辑
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="pt-2">
          <div className="flex items-center gap-2 mb-4">
            <div className="text-sm font-semibold text-gray-800 dark:text-gray-100">
              已创建的 Agent
            </div>
            <div className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
              {customAgents.length}
            </div>
          </div>
          <div className="space-y-2">
            {customAgents.length === 0 ? (
              <div className="p-4 rounded-lg border border-dashed border-gray-200 dark:border-gray-700 text-sm text-gray-500 dark:text-gray-400 text-center">
                暂无自定义 Agent
              </div>
            ) : (
              customAgents.map((agent) => (
                <div
                  key={agent.name}
                  className="flex items-center justify-between gap-3 rounded-lg border border-gray-200/60 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 px-4 py-3 hover:shadow-md hover:border-purple-300/60 dark:hover:border-purple-700/60 transition-all duration-200"
                >
                  <div>
                    <div className="text-sm font-medium text-gray-800 dark:text-gray-100">
                      {agent.display_name}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">
                      {agent.name}
                    </div>
                    {agent.tools.length > 0 && (
                      <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        Tools: {agent.tools.join(', ')}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-xs px-2 py-1 rounded-full font-medium ${
                        agent.enabled
                          ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400'
                          : 'bg-gray-200 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
                      }`}
                    >
                      {agent.enabled ? '已启用' : '已禁用'}
                    </span>
                    <button
                      onClick={() => onEdit(agent)}
                      disabled={loading}
                      className="p-2 rounded-lg text-gray-500 hover:text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-900/30 transition-all duration-200"
                      aria-label={`Edit ${agent.display_name}`}
                    >
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => onDelete(agent.name)}
                      disabled={loading}
                      className="p-2 rounded-lg text-gray-500 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 transition-all duration-200"
                      aria-label={`Delete ${agent.display_name}`}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </>
  );
}
