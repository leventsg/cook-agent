/**
 * Tool Selector Component
 *
 * Tools/MCP/Agents 分为独立方框：
 * - Tools 方框：展示 builtin server，点击展开显示工具列表
 * - MCP 方框：展示 MCP servers，点击展开显示工具列表
 * - Agents 方框：展示 Subagent，点击展开显示列表
 *
 * Tools/MCP 使用统一的 ServerCard 组件展示。
 */

import { useState, useEffect, useCallback, useRef, memo, useMemo } from 'react';
import { ChevronDown, ChevronUp, Wrench, Globe, Check, Info, Bot, Loader2 } from 'lucide-react';
import type { ServerInfo, ToolSchema, SubagentSchema } from '../../types';
import { getAvailableTools, listSubagents, toggleSubagent } from '../../services/api/agent';

export interface ToolSelectorProps {
  token?: string;
  selectedTools: string[];
  onSelectionChange: (tools: string[]) => void;
  disabled?: boolean;
  onExpandChange?: (isExpanded: boolean) => void;
}

// Compact tool chip component
const ToolChip = memo(function ToolChip({
  tool,
  isSelected,
  onToggle,
  onShowInfo,
  isShowingInfo,
  disabled,
  serverType
}: {
  tool: ToolSchema;
  isSelected: boolean;
  onToggle: () => void;
  onShowInfo: () => void;
  isShowingInfo: boolean;
  disabled?: boolean;
  serverType: string;
}) {
  // For MCP tools, remove prefix for shorter display
  const displayName = serverType === 'mcp'
    ? tool.name.replace(/^mcp_\w+_/, '')
    : tool.name;

  // Colors based on server type
  const isLocal = serverType === 'local';
  const selectedBgClass = isLocal ? 'bg-orange-500' : 'bg-blue-500';
  const hoverTextClass = isLocal ? 'hover:text-orange-600 dark:hover:text-orange-400' : 'hover:text-blue-600 dark:hover:text-blue-400';
  const infoHoverClass = isLocal ? 'hover:text-orange-500' : 'hover:text-blue-500';
  const infoSelectedClass = isLocal ? 'text-orange-200' : 'text-blue-200';

  return (
    <div
      className={`
        inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs
        transition-colors duration-150
        ${disabled ? 'opacity-50' : ''}
        ${isSelected
          ? `${selectedBgClass} text-white`
          : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
        }
      `}
    >
      {/* Checkbox area */}
      <div
        onClick={() => !disabled && onToggle()}
        className={`
          flex items-center gap-1 cursor-pointer
          ${!isSelected ? hoverTextClass : ''}
        `}
      >
        {isSelected && <Check className="w-3 h-3" />}
        <span>{displayName}</span>
      </div>

      {/* Info icon */}
      {tool.description && (
        <Info
          onClick={(e) => {
            e.stopPropagation();
            onShowInfo();
          }}
          className={`
            w-3 h-3 cursor-pointer flex-shrink-0
            ${isShowingInfo
              ? 'text-yellow-300'
              : isSelected
                ? `${infoSelectedClass} hover:text-white`
                : `text-gray-400 ${infoHoverClass}`
            }
          `}
        />
      )}
    </div>
  );
});

// Subagent chip component
const SubagentChip = memo(function SubagentChip({
  subagent,
  isSelected,
  onToggle,
  onShowInfo,
  isShowingInfo,
  disabled,
  isToggling,
}: {
  subagent: SubagentSchema;
  isSelected: boolean;
  onToggle: () => void;
  onShowInfo: () => void;
  isShowingInfo: boolean;
  disabled?: boolean;
  isToggling?: boolean;
}) {
  return (
    <div
      className={`
        inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs
        transition-colors duration-150 select-none
        ${disabled || isToggling ? 'opacity-50' : ''}
        ${isSelected
          ? 'bg-purple-500 text-white'
          : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
        }
      `}
    >
      {/* Checkbox area */}
      <div
        onClick={() => !disabled && !isToggling && onToggle()}
        className={`
          flex items-center gap-1 cursor-pointer
          ${!isSelected ? 'hover:text-purple-600 dark:hover:text-purple-400' : ''}
        `}
      >
        {isToggling ? (
          <Loader2 className="w-3 h-3 animate-spin" />
        ) : isSelected ? (
          <Check className="w-3 h-3" />
        ) : null}
        <span className="font-medium">{subagent.display_name}</span>
      </div>

      {/* Info icon */}
      {subagent.description && (
        <Info
          onClick={(e) => {
            e.stopPropagation();
            onShowInfo();
          }}
          className={`
            w-3 h-3 cursor-pointer flex-shrink-0
            ${isShowingInfo
              ? 'text-yellow-300'
              : isSelected
                ? 'text-purple-200 hover:text-white'
                : 'text-gray-400 hover:text-purple-500'
            }
          `}
        />
      )}
    </div>
  );
});

// Server card component - works for both builtin and MCP servers
const ServerCard = memo(function ServerCard({
  server,
  selectedTools,
  onToggleTool,
  onToggleAll,
  disabled,
  isExpanded,
  onToggleExpand,
}: {
  server: ServerInfo;
  selectedTools: string[];
  onToggleTool: (name: string) => void;
  onToggleAll: (serverName: string, select: boolean) => void;
  disabled?: boolean;
  isExpanded: boolean;
  onToggleExpand: () => void;
}) {
  const [showingInfoTool, setShowingInfoTool] = useState<string | null>(null);

  const selectedCount = server.tools.filter(t => selectedTools.includes(t.name)).length;
  const allSelected = selectedCount === server.tools.length && server.tools.length > 0;

  // Find the tool whose info is being shown
  const infoTool = showingInfoTool ? server.tools.find(t => t.name === showingInfoTool) : null;

  // Choose icon and colors based on server type
  const ServerIcon = server.type === 'local' ? Wrench : Globe;
  const iconColorClass = server.type === 'local' ? 'text-orange-500' : 'text-blue-500';
  const buttonColorClass = server.type === 'local'
    ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 hover:bg-orange-200 dark:hover:bg-orange-900/50'
    : 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/50';

  const handleShowInfo = (toolName: string) => {
    setShowingInfoTool(prev => prev === toolName ? null : toolName);
  };

  return (
    <div className="border border-gray-200 dark:border-gray-600 rounded-lg overflow-hidden">
      {/* Server header */}
      <div
        className="flex items-center gap-2 px-3 py-2 bg-gray-50 dark:bg-gray-700/50 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700"
        onClick={onToggleExpand}
      >
        <ServerIcon className={`w-3.5 h-3.5 ${iconColorClass}`} />
        <span className="text-xs font-medium text-gray-700 dark:text-gray-300 flex-1">
          {server.name}
        </span>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {selectedCount}/{server.tools.length}
        </span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleAll(server.name, !allSelected);
          }}
          disabled={disabled}
          className={`
            px-2 py-0.5 text-xs rounded transition-colors
            ${allSelected
              ? buttonColorClass
              : 'bg-gray-100 dark:bg-gray-600 text-gray-600 dark:text-gray-400'
            }
            hover:opacity-80
          `}
        >
          {allSelected ? 'Deselect All' : 'Select All'}
        </button>
        {isExpanded ? (
          <ChevronUp className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        )}
      </div>

      {/* Expanded tool list */}
      {isExpanded && (
        <div className="p-2 bg-gray-50 dark:bg-gray-800">
          {/* Tool chips - compact flex wrap layout */}
          <div className="flex flex-wrap gap-1.5">
            {server.tools.map(tool => (
              <ToolChip
                key={tool.name}
                tool={tool}
                isSelected={selectedTools.includes(tool.name)}
                onToggle={() => onToggleTool(tool.name)}
                onShowInfo={() => handleShowInfo(tool.name)}
                isShowingInfo={showingInfoTool === tool.name}
                disabled={disabled}
                serverType={server.type}
              />
            ))}
            {server.tools.length === 0 && (
              <span className="text-xs text-gray-400">No tools available</span>
            )}
          </div>

          {/* Tool description - shown at bottom when info icon is clicked */}
          {infoTool && infoTool.description && (
            <div className="mt-2 p-2 bg-gray-100 dark:bg-gray-700 rounded-lg">
              <div className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                {infoTool.name}
              </div>
              <div className="text-xs text-gray-600 dark:text-gray-400">
                {infoTool.description}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
});

export function ToolSelector({
  token,
  selectedTools,
  onSelectionChange,
  disabled = false,
  onExpandChange,
}: ToolSelectorProps) {
  const [isToolsExpanded, setIsToolsExpanded] = useState(false);
  const [isMCPExpanded, setIsMCPExpanded] = useState(false);
  const [isAgentsExpanded, setIsAgentsExpanded] = useState(false);
  const [servers, setServers] = useState<ServerInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedServers, setExpandedServers] = useState<Set<string>>(new Set());
  const [subagents, setSubagents] = useState<SubagentSchema[]>([]);
  const [isSubagentLoading, setIsSubagentLoading] = useState(false);
  const [subagentError, setSubagentError] = useState<string | null>(null);
  const [showingInfoAgent, setShowingInfoAgent] = useState<string | null>(null);
  const [togglingAgents, setTogglingAgents] = useState<Set<string>>(new Set());
  const selectedToolsRef = useRef<string[]>(selectedTools);

  // Load available tools
  const loadTools = useCallback(async () => {
    if (!token) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await getAvailableTools(token);
      setServers(response.servers);

      // Always enable builtin tools on load
      if (response.servers.length > 0) {
        const builtinToolNames = response.servers
          .filter(server => server.type === 'local')
          .flatMap(server => server.tools.map(tool => tool.name));
        const builtinSet = new Set(builtinToolNames);
        const mergedSelection = [
          ...selectedToolsRef.current.filter((name) => !builtinSet.has(name)),
          ...builtinToolNames,
        ];
        const hasDiff =
          mergedSelection.length !== selectedToolsRef.current.length ||
          mergedSelection.some(
            (name, index) => name !== selectedToolsRef.current[index]
          );
        if (hasDiff) {
          onSelectionChange(mergedSelection);
        }
      }
    } catch (err) {
      console.error('Failed to load tools:', err);
      setError(err instanceof Error ? err.message : 'Failed to load tools');
    } finally {
      setIsLoading(false);
    }
  }, [token, onSelectionChange]);

  const loadSubagents = useCallback(async () => {
    if (!token) return;

    setIsSubagentLoading(true);
    setSubagentError(null);

    try {
      const response = await listSubagents(token);
      setSubagents(response.subagents);

      const enabledSubagentTools = response.subagents
        .filter((subagent) => subagent.enabled)
        .map((subagent) => `subagent_${subagent.name}`);
      const enabledSet = new Set(enabledSubagentTools);

      const cleanedSelection = selectedToolsRef.current.filter(
        (toolName) =>
          !toolName.startsWith('subagent_') || enabledSet.has(toolName)
      );
      const mergedSelection = [...cleanedSelection];

      enabledSubagentTools.forEach((name) => {
        if (!mergedSelection.includes(name)) {
          mergedSelection.push(name);
        }
      });

      const hasDiff =
        mergedSelection.length !== selectedToolsRef.current.length ||
        mergedSelection.some(
          (name, index) => name !== selectedToolsRef.current[index]
        );

      if (hasDiff) {
        onSelectionChange(mergedSelection);
      }
    } catch (err) {
      console.error('Failed to load subagents:', err);
      setSubagentError(err instanceof Error ? err.message : 'Failed to load subagents');
    } finally {
      setIsSubagentLoading(false);
    }
  }, [token, onSelectionChange]);

  useEffect(() => {
    loadTools();
  }, [loadTools]);

  useEffect(() => {
    loadSubagents();
  }, [loadSubagents]);

  useEffect(() => {
    if (isAgentsExpanded) {
      loadSubagents();
    }
  }, [isAgentsExpanded, loadSubagents]);

  useEffect(() => {
    selectedToolsRef.current = selectedTools;
  }, [selectedTools]);

  useEffect(() => {
    onExpandChange?.(isToolsExpanded || isMCPExpanded || isAgentsExpanded);
  }, [isToolsExpanded, isMCPExpanded, isAgentsExpanded, onExpandChange]);

  useEffect(() => () => onExpandChange?.(false), [onExpandChange]);

  const handleToggleTool = useCallback((toolName: string) => {
    if (disabled) return;

    if (selectedTools.includes(toolName)) {
      onSelectionChange(selectedTools.filter(t => t !== toolName));
    } else {
      onSelectionChange([...selectedTools, toolName]);
    }
  }, [disabled, selectedTools, onSelectionChange]);

  const handleToggleServer = useCallback((serverName: string, select: boolean) => {
    if (disabled) return;

    const server = servers.find(s => s.name === serverName);
    if (!server) return;

    const serverToolNames = server.tools.map(t => t.name);

    if (select) {
      const newSelection = [...selectedTools];
      serverToolNames.forEach(name => {
        if (!newSelection.includes(name)) {
          newSelection.push(name);
        }
      });
      onSelectionChange(newSelection);
    } else {
      onSelectionChange(selectedTools.filter(t => !serverToolNames.includes(t)));
    }
  }, [disabled, servers, selectedTools, onSelectionChange]);

  const handleToggleExpandServer = useCallback((serverName: string) => {
    setExpandedServers(prev => {
      const next = new Set(prev);
      if (next.has(serverName)) {
        next.delete(serverName);
      } else {
        next.add(serverName);
      }
      return next;
    });
  }, []);

  const handleToggleSubagent = useCallback(async (subagent: SubagentSchema) => {
    if (disabled || !token) return;

    const toolName = `subagent_${subagent.name}`;
    const isSelected = selectedTools.includes(toolName);
    const newEnabled = !isSelected;

    if (newEnabled) {
      onSelectionChange([...selectedTools, toolName]);
    } else {
      onSelectionChange(selectedTools.filter(t => t !== toolName));
    }

    setSubagents(prev =>
      prev.map(agent =>
        agent.name === subagent.name ? { ...agent, enabled: newEnabled } : agent
      )
    );

    setTogglingAgents(prev => new Set(prev).add(subagent.name));

    try {
      await toggleSubagent(subagent.name, newEnabled, token);
    } catch (err) {
      console.error('Failed to toggle subagent:', err);

      if (newEnabled) {
        onSelectionChange(selectedTools.filter(t => t !== toolName));
      } else {
        onSelectionChange([...selectedTools, toolName]);
      }

      setSubagents(prev =>
        prev.map(agent =>
          agent.name === subagent.name ? { ...agent, enabled: !newEnabled } : agent
        )
      );
    } finally {
      setTogglingAgents(prev => {
        const next = new Set(prev);
        next.delete(subagent.name);
        return next;
      });
    }
  }, [disabled, token, selectedTools, onSelectionChange]);

  const handleShowAgentInfo = useCallback((name: string) => {
    setShowingInfoAgent(prev => (prev === name ? null : name));
  }, []);

  // Separate builtin and MCP servers
  const { builtinServers, mcpServers } = useMemo(() => ({
    builtinServers: servers.filter(s => s.type === 'local'),
    mcpServers: servers.filter(s => s.type === 'mcp'),
  }), [servers]);

  // Calculate selected counts
  const builtinTools = builtinServers.flatMap(s => s.tools);
  const mcpTools = mcpServers.flatMap(s => s.tools);
  const builtinSelectedCount = builtinTools.filter(t => selectedTools.includes(t.name)).length;
  const mcpSelectedCount = mcpTools.filter(t => selectedTools.includes(t.name)).length;
  const subagentSelectedCount = subagents.filter(s =>
    selectedTools.includes(`subagent_${s.name}`)
  ).length;
  const hasSubagents = isSubagentLoading || subagentError !== null || subagents.length > 0;
  const infoAgent = showingInfoAgent
    ? subagents.find(agent => agent.name === showingInfoAgent)
    : null;

  return (
    <div className="mb-2">
      {/* ========== Header Row ========== */}
      <div className="flex items-center gap-3 mb-2">
        {/* Tools Header */}
        <button
          onClick={() => {
            setIsToolsExpanded(!isToolsExpanded);
            if (!isToolsExpanded) {
              setIsMCPExpanded(false);
              setIsAgentsExpanded(false);
            }
          }}
          disabled={isLoading}
          className={`
            flex items-center gap-2 px-3 py-2 rounded-lg text-sm
            transition-colors duration-150 whitespace-nowrap
            ${isLoading
              ? 'text-gray-400 cursor-not-allowed'
              : isToolsExpanded
                ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-200'
                : 'text-gray-700 dark:text-gray-300 hover:bg-orange-50 dark:hover:bg-orange-900/20'
            }
          `}
        >
          <Wrench className="w-4 h-4 text-orange-500" />
          <span className="font-medium">Tools</span>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            ({builtinSelectedCount}/{builtinTools.length})
          </span>
          {isToolsExpanded ? (
            <ChevronUp className="w-4 h-4" />
          ) : (
            <ChevronDown className="w-4 h-4" />
          )}
        </button>

        {/* MCP Header */}
        {mcpServers.length > 0 && (
          <button
            onClick={() => {
              setIsMCPExpanded(!isMCPExpanded);
              if (!isMCPExpanded) {
                setIsToolsExpanded(false);
                setIsAgentsExpanded(false);
              }
            }}
            disabled={isLoading}
            className={`
              flex items-center gap-2 px-3 py-2 rounded-lg text-sm
              transition-colors duration-150 whitespace-nowrap
              ${isLoading
                ? 'text-gray-400 cursor-not-allowed'
                : isMCPExpanded
                  ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-blue-50 dark:hover:bg-blue-900/20'
              }
            `}
          >
            <Globe className="w-4 h-4 text-blue-500" />
            <span className="font-medium">MCP</span>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              ({mcpSelectedCount}/{mcpTools.length})
            </span>
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {mcpServers.length} server{mcpServers.length > 1 ? 's' : ''}
            </span>
            {isMCPExpanded ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>
        )}

        {/* Agents Header */}
        {hasSubagents && (
          <button
            onClick={() => {
              setIsAgentsExpanded(!isAgentsExpanded);
              if (!isAgentsExpanded) {
                setIsToolsExpanded(false);
                setIsMCPExpanded(false);
              }
            }}
            disabled={isSubagentLoading}
            className={`
              flex items-center gap-2 px-3 py-2 rounded-lg text-sm
              transition-colors duration-150 whitespace-nowrap
              ${isSubagentLoading
                ? 'text-gray-400 cursor-not-allowed'
                : isAgentsExpanded
                  ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-purple-50 dark:hover:bg-purple-900/20'
              }
            `}
          >
            <Bot className="w-4 h-4 text-purple-500" />
            <span className="font-medium">Agents</span>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              ({subagentSelectedCount}/{subagents.length})
            </span>
            {isAgentsExpanded ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>
        )}
      </div>

      {/* ========== Single Expanded Panel ========== */}
      {(isToolsExpanded || isMCPExpanded || isAgentsExpanded) && (
        <div className="bg-gray-50/50 dark:bg-gray-800/50 rounded-lg border border-gray-200 dark:border-gray-600 p-3 space-y-2">
          {/* Tools Expanded Panel */}
          {isToolsExpanded && (
            <>
              {isLoading ? (
                <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-2">
                  Loading tools...
                </div>
              ) : error ? (
                <div className="text-sm text-red-500 text-center py-2">
                  {error}
                </div>
              ) : builtinServers.length > 0 ? (
                builtinServers.map(server => (
                  <ServerCard
                    key={server.name}
                    server={server}
                    selectedTools={selectedTools}
                    onToggleTool={handleToggleTool}
                    onToggleAll={handleToggleServer}
                    disabled={disabled}
                    isExpanded={expandedServers.has(server.name)}
                    onToggleExpand={() => handleToggleExpandServer(server.name)}
                  />
                ))
              ) : (
                <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-2">
                  No built-in tools available
                </div>
              )}
            </>
          )}

          {/* MCP Expanded Panel */}
          {isMCPExpanded && (
            <>
              {mcpServers.map(server => (
                <ServerCard
                  key={server.name}
                  server={server}
                  selectedTools={selectedTools}
                  onToggleTool={handleToggleTool}
                  onToggleAll={handleToggleServer}
                  disabled={disabled}
                  isExpanded={expandedServers.has(server.name)}
                  onToggleExpand={() => handleToggleExpandServer(server.name)}
                />
              ))}
            </>
          )}

          {/* Agents Expanded Panel */}
          {isAgentsExpanded && (
            <>
              {isSubagentLoading ? (
                <div className="flex items-center justify-center gap-2 py-2">
                  <Loader2 className="w-4 h-4 animate-spin text-purple-500" />
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    Loading agents...
                  </span>
                </div>
              ) : subagentError ? (
                <div className="text-sm text-red-500 text-center py-2">
                  {subagentError}
                </div>
              ) : subagents.length > 0 ? (
                <>
                  <div className="flex flex-wrap gap-1.5">
                    {subagents.map(subagent => (
                      <SubagentChip
                        key={subagent.name}
                        subagent={subagent}
                        isSelected={selectedTools.includes(
                          `subagent_${subagent.name}`
                        )}
                        onToggle={() => handleToggleSubagent(subagent)}
                        onShowInfo={() => handleShowAgentInfo(subagent.name)}
                        isShowingInfo={showingInfoAgent === subagent.name}
                        disabled={disabled}
                        isToggling={togglingAgents.has(subagent.name)}
                      />
                    ))}
                  </div>

                  {infoAgent && (
                    <div className="mt-3 p-3 bg-gray-100 dark:bg-gray-700 rounded-lg">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                          {infoAgent.display_name}
                        </span>
                        {infoAgent.builtin && (
                          <span className="text-xs px-1.5 py-0.5 bg-purple-100 dark:bg-purple-900/50 text-purple-600 dark:text-purple-300 rounded">
                            Built-in
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">
                        {infoAgent.description}
                      </p>
                      {infoAgent.tools.length > 0 && (
                        <div className="text-xs text-gray-500 dark:text-gray-500">
                          <span className="font-medium">Tools:</span>{' '}
                          {infoAgent.tools.join(', ')}
                        </div>
                      )}
                    </div>
                  )}
                </>
              ) : (
                <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-2">
                  No agents available
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
