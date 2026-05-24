/**
 * API Services - Central export
 */

// Re-export all API functions
export * from './client';
export * from './auth';
export * from './user';
export * from './conversation';
export * from './knowledge';
export * from './evaluation';
export * from './agent';


// Named exports for backward compatibility
export {
  login as loginUser,
  register as registerUser,
} from './auth';

export {
  getProfile,
  updateProfile,
} from './user';

export {
  listPersonalDocuments,
  createPersonalDocument,
  getKnowledgeMetadataOptions,
} from './knowledge';

export {
  streamConversation,
  getConversationHistory,
  listConversations,
  deleteConversation,
  updateConversationTitle,
} from './conversation';
