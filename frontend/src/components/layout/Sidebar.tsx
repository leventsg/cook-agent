/**
 * Sidebar Component
 * Navigation sidebar with conversation list and user profile
 */

import {
    MessageSquare,
    Plus,
    PanelLeftClose,
    MoreHorizontal,
    Trash2,
    Pencil,
    Check,
    X,
    ChevronDown,
    Bot, // New Icon
} from 'lucide-react';
import { useState, useRef, useEffect, useMemo } from 'react';
import { ThemeToggle } from '../common/ThemeToggle';
import { UserProfileModal } from './UserProfileModal';
import { useAuth } from '../../contexts';
import { getDateCategory, DATE_CATEGORY_LABELS } from '../../utils';
import type { ConversationSummary } from '../../types';

// Date category types
type DateCategory = 'today' | 'yesterday' | 'lastWeek' | 'lastMonth' | 'older';

interface GroupedConversations {
    category: DateCategory;
    label: string;
    conversations: ConversationSummary[];
}

const categoryOrder: DateCategory[] = [
    'today',
    'yesterday',
    'lastWeek',
    'lastMonth',
    'older',
];

export interface SidebarProps {
    isOpen: boolean;
    toggleSidebar: () => void;
    conversations: ConversationSummary[];
    totalConversations?: number;
    hasMoreConversations?: boolean;
    onLoadMoreConversations?: () => void;
    currentConversationId: string | null;
    onSelectConversation: (id: string) => void;
    onNewChat: () => void;
    onDeleteConversation?: (id: string) => Promise<boolean>;
    onRenameConversation?: (id: string, newTitle: string) => Promise<boolean>;
    isDark: boolean;
    toggleTheme: () => void;
    
    // Agent specific
    isAgentMode?: boolean;
    onToggleAgentMode?: () => void;
}

export function Sidebar({
    isOpen,
    toggleSidebar,
    conversations,
    totalConversations = 0,
    hasMoreConversations = false,
    onLoadMoreConversations,
    currentConversationId,
    onSelectConversation,
    onNewChat,
    onDeleteConversation,
    onRenameConversation,
    isDark,
    toggleTheme,
    isAgentMode,
    onToggleAgentMode
}: SidebarProps) {
    const { username } = useAuth();
    const [profileOpen, setProfileOpen] = useState(false);
    const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editingTitle, setEditingTitle] = useState('');
    const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
    const menuRef = useRef<HTMLDivElement>(null);
    const editInputRef = useRef<HTMLInputElement>(null);

    // Group conversations by date
    const groupedConversations = useMemo((): GroupedConversations[] => {
        const groups: Record<DateCategory, ConversationSummary[]> = {
            today: [],
            yesterday: [],
            lastWeek: [],
            lastMonth: [],
            older: [],
        };

        conversations.forEach((conv) => {
            const category = getDateCategory(conv.updated_at) as DateCategory;
            groups[category].push(conv);
        });

        return categoryOrder
            .filter((cat) => groups[cat].length > 0)
            .map((cat) => ({
                category: cat,
                label: DATE_CATEGORY_LABELS[cat],
                conversations: groups[cat],
            }));
    }, [conversations]);

    // Close menu when clicking outside
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
                setMenuOpenId(null);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    // Focus input when editing starts
    useEffect(() => {
        if (editingId && editInputRef.current) {
            editInputRef.current.focus();
            editInputRef.current.select();
        }
    }, [editingId]);

    const handleMenuClick = (e: React.MouseEvent, convId: string) => {
        e.stopPropagation();
        setMenuOpenId(menuOpenId === convId ? null : convId);
        setDeleteConfirmId(null);
    };

    const handleRenameClick = (e: React.MouseEvent, conv: ConversationSummary) => {
        e.stopPropagation();
        setEditingId(conv.id);
        setEditingTitle(conv.title || conv.last_message_preview || 'New Conversation');
        setMenuOpenId(null);
    };

    const handleRenameSave = async (id: string) => {
        if (onRenameConversation && editingTitle.trim()) {
            await onRenameConversation(id, editingTitle.trim());
        }
        setEditingId(null);
        setEditingTitle('');
    };

    const handleRenameCancel = () => {
        setEditingId(null);
        setEditingTitle('');
    };

    const handleDeleteClick = (e: React.MouseEvent, convId: string) => {
        e.stopPropagation();
        setDeleteConfirmId(convId);
    };

    const handleDeleteConfirm = async (e: React.MouseEvent, id: string) => {
        e.stopPropagation();
        if (onDeleteConversation) {
            await onDeleteConversation(id);
        }
        setMenuOpenId(null);
        setDeleteConfirmId(null);
    };

    const handleDeleteCancel = (e: React.MouseEvent) => {
        e.stopPropagation();
        setDeleteConfirmId(null);
    };

    return (
        <>
            {/* Mobile Overlay */}
            {isOpen && (
                <div
                    className="fixed inset-0 bg-black/50 backdrop-blur-sm z-20 md:hidden"
                    onClick={toggleSidebar}
                    aria-hidden="true"
                />
            )}

            {/* Sidebar Container */}
            <div
                className={`
          fixed md:static inset-y-0 left-0 z-30
          flex flex-col flex-none
          bg-gradient-to-b from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-950
          border-r border-gray-200 dark:border-gray-800
          transform transition-all duration-300 ease-in-out shadow-xl md:shadow-none
          ${isOpen
                        ? 'translate-x-0 w-72 md:w-72'
                        : '-translate-x-full md:-translate-x-full md:w-0 md:opacity-0 md:pointer-events-none'
                    }
        `}
                role="navigation"
                aria-label="Sidebar"
            >
                {/* Header */}
                <SidebarHeader 
                    toggleSidebar={toggleSidebar} 
                    onNewChat={onNewChat}
                    isAgentMode={isAgentMode}
                    onToggleAgentMode={onToggleAgentMode} 
                />

                {/* Conversation List */}
                <div className="flex-1 overflow-y-auto px-3 py-3 space-y-1">
                    <div className="flex items-center justify-between px-2 mb-2">
                        <p className="text-xs text-gray-400 dark:text-gray-500 font-medium uppercase tracking-wider">
                            {isAgentMode ? 'Recent Agent Sessions' : 'Recent Chats'}
                        </p>
                        {totalConversations > 0 && (
                            <span className="text-xs text-gray-400 dark:text-gray-500 bg-gray-200 dark:bg-gray-700 px-1.5 py-0.5 rounded-full">
                                {totalConversations}
                            </span>
                        )}
                    </div>

                    {groupedConversations.map((group) => (
                        <div key={group.category} className="mb-2">
                            <p className="text-xs text-gray-400 dark:text-gray-500 px-2 py-1 font-medium">
                                {group.label}
                            </p>

                            {group.conversations.map((conv) => (
                                <ConversationItem
                                    key={conv.id}
                                    conversation={conv}
                                    isActive={currentConversationId === conv.id}
                                    isAgentMode={isAgentMode}
                                    isEditing={editingId === conv.id}
                                    editingTitle={editingTitle}
                                    menuOpen={menuOpenId === conv.id}
                                    deleteConfirm={deleteConfirmId === conv.id}
                                    onSelect={() => onSelectConversation(conv.id)}
                                    onMenuClick={(e) => handleMenuClick(e, conv.id)}
                                    onRenameClick={(e) => handleRenameClick(e, conv)}
                                    onRenameSave={() => handleRenameSave(conv.id)}
                                    onRenameCancel={handleRenameCancel}
                                    onEditingTitleChange={setEditingTitle}
                                    onDeleteClick={(e) => handleDeleteClick(e, conv.id)}
                                    onDeleteConfirm={(e) => handleDeleteConfirm(e, conv.id)}
                                    onDeleteCancel={handleDeleteCancel}
                                    menuRef={menuRef}
                                    editInputRef={editInputRef}
                                />
                            ))}
                        </div>
                    ))}

                    {/* Load More Button */}
                    {hasMoreConversations && onLoadMoreConversations && (
                        <button
                            onClick={onLoadMoreConversations}
                            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-xs text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
                        >
                            <ChevronDown className="w-4 h-4" />
                            Load more
                        </button>
                    )}

                    {/* Empty State */}
                    {conversations.length === 0 && (
                        <div className="text-center text-gray-400 dark:text-gray-500 text-sm py-12">
                            <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
                            <p>No conversations yet</p>
                            <p className="text-xs mt-1">Start a new chat to begin!</p>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <SidebarFooter
                    username={username}
                    isDark={isDark}
                    toggleTheme={toggleTheme}
                    onProfileClick={() => setProfileOpen(true)}
                />

                <UserProfileModal open={profileOpen} onClose={() => setProfileOpen(false)} />
            </div>
        </>
    );
}

/**
 * Sidebar header with logo and new chat button
 */
function SidebarHeader({
    toggleSidebar,
    onNewChat,
    isAgentMode,
    onToggleAgentMode,
}: {
    toggleSidebar: () => void;
    onNewChat: () => void;
    isAgentMode?: boolean;
    onToggleAgentMode?: () => void;
}) {
    return (
        <div className="p-4 border-b border-gray-200 dark:border-gray-800">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 flex items-center justify-center">
                        <img
                            src="/logo.png"
                            alt="CookHero Logo"
                            className="w-full h-full object-contain"
                        />
                    </div>
                    <span className="font-bold text-gray-800 dark:text-gray-100">CookHero</span>
                    
                    {onToggleAgentMode && (
                        <button
                            onClick={onToggleAgentMode}
                            className={`ml-2 flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border transition-colors bg-orange-100 text-orange-600 border-orange-200 dark:bg-orange-900/30 dark:text-orange-400 dark:border-orange-800 hover:bg-orange-200 dark:hover:bg-orange-800
                            `}
                            title={isAgentMode ? "Switch to standard chat" : "Switch to Agent mode"}
                        >
                            {isAgentMode ? <Bot className="w-3 h-3" /> : <MessageSquare className="w-3 h-3" />}
                            {isAgentMode ? 'Agent Mode' : '\u00A0Chat Mode'}
                        </button>
                    )}
                </div>
                <button
                    onClick={toggleSidebar}
                    className="md:hidden p-2 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-800 rounded-lg transition-colors"
                    aria-label="Close sidebar"
                >
                    <PanelLeftClose className="w-5 h-5" />
                </button>
            </div>
            <button
                onClick={onNewChat}
                className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 text-white rounded-xl text-sm font-medium shadow-sm transition-all duration-200 hover:shadow-md bg-gradient-to-r from-orange-400 to-orange-500 hover:from-orange-500 hover:to-orange-600
                `}
            >
                <Plus className="w-4 h-4" />
                {isAgentMode ? 'New Agent Session' : 'New Chat Session'}
            </button>
        </div>
    );
}

/**
 * Sidebar footer with user profile and theme toggle
 */
function SidebarFooter({
    username,
    isDark,
    toggleTheme,
    onProfileClick,
}: {
    username: string | null;
    isDark: boolean;
    toggleTheme: () => void;
    onProfileClick: () => void;
}) {
    return (
        <div className="p-4 border-t border-gray-200 dark:border-gray-800 bg-white/50 dark:bg-gray-900/50">
            <div className="flex items-center justify-between">
                <button
                    onClick={onProfileClick}
                    className="flex items-center gap-3 focus:outline-none"
                >
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center text-white font-bold text-xs shadow-sm">
                        {username ? username.charAt(0).toUpperCase() : 'U'}
                    </div>
                    <div className="text-left">
                        <div className="font-medium text-gray-900 dark:text-white text-sm">
                            {username || 'User'}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                            View & edit profile
                        </div>
                    </div>
                </button>
                <ThemeToggle isDark={isDark} toggleTheme={toggleTheme} />
            </div>
        </div>
    );
}

/**
 * Individual conversation item
 */
function ConversationItem({
    conversation,
    isActive,
    isAgentMode,
    isEditing,
    editingTitle,
    menuOpen,
    deleteConfirm,
    onSelect,
    onMenuClick,
    onRenameClick,
    onRenameSave,
    onRenameCancel,
    onEditingTitleChange,
    onDeleteClick,
    onDeleteConfirm,
    onDeleteCancel,
    menuRef,
    editInputRef,
}: {
    conversation: ConversationSummary;
    isActive: boolean;
    isAgentMode?: boolean;
    isEditing: boolean;
    editingTitle: string;
    menuOpen: boolean;
    deleteConfirm: boolean;
    onSelect: () => void;
    onMenuClick: (e: React.MouseEvent) => void;
    onRenameClick: (e: React.MouseEvent) => void;
    onRenameSave: () => void;
    onRenameCancel: () => void;
    onEditingTitleChange: (title: string) => void;
    onDeleteClick: (e: React.MouseEvent) => void;
    onDeleteConfirm: (e: React.MouseEvent) => void;
    onDeleteCancel: (e: React.MouseEvent) => void;
    menuRef: React.RefObject<HTMLDivElement | null>;
    editInputRef: React.RefObject<HTMLInputElement | null>;
}) {
    const [isComposing, setIsComposing] = useState(false);
    const displayTitle =
        conversation.title || conversation.last_message_preview || 'New Conversation';

    if (isEditing) {
        return (
            <div className={`flex items-center gap-2 px-3 py-2.5 rounded-xl bg-white dark:bg-gray-800 border ${isAgentMode ? 'border-orange-400 dark:border-orange-500' : 'border-orange-400 dark:border-orange-500'}`}>
                <MessageSquare className={`w-4 h-4 shrink-0 ${isAgentMode ? 'text-orange-500' : 'text-orange-500'}`} />
                <input
                    ref={editInputRef}
                    type="text"
                    value={editingTitle}
                    onChange={(e) => onEditingTitleChange(e.target.value)}
                    onCompositionStart={() => setIsComposing(true)}
                    onCompositionEnd={() => setIsComposing(false)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter' && !isComposing) onRenameSave();
                        if (e.key === 'Escape') onRenameCancel();
                    }}
                    className="flex-1 bg-transparent text-sm text-gray-900 dark:text-white outline-none"
                />
                <button
                    onClick={onRenameSave}
                    className="p-1 text-green-600 hover:text-green-700 dark:text-green-500 dark:hover:text-green-400"
                    aria-label="Save"
                >
                    <Check className="w-4 h-4" />
                </button>
                <button
                    onClick={onRenameCancel}
                    className="p-1 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                    aria-label="Cancel"
                >
                    <X className="w-4 h-4" />
                </button>
            </div>
        );
    }

    return (
        <div className="relative group">
            <button
                onClick={onSelect}
                className={`
          w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left text-sm transition-all duration-200
          ${isActive
                        ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white font-medium shadow-sm border border-gray-200 dark:border-gray-700'
                        : 'text-gray-600 dark:text-gray-400 hover:bg-white/50 dark:hover:bg-gray-800/50'
                    }
        `}
            >
                <MessageSquare
                    className={`w-4 h-4 shrink-0 ${isActive ? (isAgentMode ? 'text-orange-500' : 'text-orange-500') : ''}`}
                />
                <span className="truncate flex-1">{displayTitle}</span>

                <div
                    onClick={onMenuClick}
                    className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-gray-200 dark:hover:bg-gray-700 transition-opacity"
                >
                    <MoreHorizontal className="w-4 h-4" />
                </div>
            </button>

            {/* Dropdown Menu */}
            {menuOpen && (
                <div
                    ref={menuRef}
                    className="absolute right-0 top-full mt-1 z-50 w-40 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-1"
                >
                    {deleteConfirm ? (
                        <div className="px-3 py-2">
                            <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">
                                Delete this chat?
                            </p>
                            <div className="flex gap-2">
                                <button
                                    onClick={onDeleteConfirm}
                                    className="flex-1 px-2 py-1 text-xs bg-red-500 hover:bg-red-600 text-white rounded transition-colors"
                                >
                                    Delete
                                </button>
                                <button
                                    onClick={onDeleteCancel}
                                    className="flex-1 px-2 py-1 text-xs bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded transition-colors"
                                >
                                    Cancel
                                </button>
                            </div>
                        </div>
                    ) : (
                        <>
                            <button
                                onClick={onRenameClick}
                                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                            >
                                <Pencil className="w-4 h-4" />
                                Rename
                            </button>
                            <button
                                onClick={onDeleteClick}
                                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-gray-100 dark:hover:bg-gray-700"
                            >
                                <Trash2 className="w-4 h-4" />
                                Delete
                            </button>
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
