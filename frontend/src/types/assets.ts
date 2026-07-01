export interface Visibility {
  owner_user_id: string;
  visibility: 'private' | 'public';
}

export interface BaseAsset {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  version: number;
  status: 'enabled' | 'disabled' | 'draft';
  visibility: Visibility['visibility'];
  owner_user_id: string;
  created_at: string;
  updated_at: string;
}

export interface SkillAsset extends BaseAsset {
  triggers?: string[];
  prompt_template?: string | null;
  mcp_tools?: string[];
  file_count: number;
  file_fingerprint: string;
}
export interface PromptAsset extends BaseAsset { content: string; }
export interface CommandAsset extends BaseAsset {
  slash_command: string;
  system_prompt_addendum: string;
  enabled: boolean;
}
export interface AgentAsset extends BaseAsset {
  system_prompt: string;
  model: string;
  tool_level: 'safe' | 'standard' | 'full';
  network: 'off' | 'local' | 'any';
  skill_codes: string[];
  mcp_server_codes: string[];
  prompt_codes: string[];
  command_codes: string[];
}