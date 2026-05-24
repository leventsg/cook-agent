/**
 * Personal knowledge base types
 */

export type KnowledgeDataSource = 'recipes' | 'tips' | 'personal';

export interface PersonalDocument {
  id: string;
  user_id?: string;
  dish_name: string;
  category: string;
  difficulty: string;
  data_source: KnowledgeDataSource;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface PersonalDocPayload {
  dish_name: string;
  category: string;
  difficulty: string;
  data_source: KnowledgeDataSource;
  content: string;
}

export interface MetadataOptions {
  dish_name: string[];
  category: string[];
  difficulty: string[];
}
