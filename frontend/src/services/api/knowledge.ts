/**
 * Knowledge base API services
 */

import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type { MetadataOptions, PersonalDocPayload, PersonalDocument } from '../../types';

export async function listPersonalDocuments(
  token?: string,
): Promise<{ items: PersonalDocument[]; limit: number; offset: number }> {
  return apiGet<{ items: PersonalDocument[]; limit: number; offset: number }>('/knowledge/personal-docs', token);
}

export async function createPersonalDocument(
  payload: PersonalDocPayload,
  token?: string,
): Promise<PersonalDocument> {
  return apiPost<PersonalDocument, PersonalDocPayload>('/knowledge/personal-docs', payload, token);
}

export async function updatePersonalDocument(
  documentId: string,
  payload: PersonalDocPayload,
  token?: string,
): Promise<PersonalDocument> {
  return apiPut<PersonalDocument, PersonalDocPayload>(`/knowledge/personal-docs/${documentId}`, payload, token);
}

export async function deletePersonalDocument(
  documentId: string,
  token?: string,
): Promise<{ success: boolean; message: string }> {
  return apiDelete<{ success: boolean; message: string }>(`/knowledge/personal-docs/${documentId}`, token);
}

export async function getKnowledgeMetadataOptions(token?: string): Promise<MetadataOptions> {
  return apiGet<MetadataOptions>('/knowledge/metadata-options', token);
}
