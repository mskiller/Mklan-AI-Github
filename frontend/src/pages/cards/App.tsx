import { useEffect, useMemo, useState } from "react";

import {
  approveImageCandidate,
  archiveProject,
  bundleExportUrl,
  characterExportImageUrl,
  characterExportJsonUrl,
  createCharacter,
  createLoreEntry,
  createProject,
  deleteCharacter,
  deleteLoreEntry,
  deleteProject,
  generateAll,
  generateGmCard,
  generateCharacterImage,
  generateCharacterImagePrompt,
  generateCharacters,
  generateLore,
  generateLoreImage,
  generateLoreImagePrompt,
  generateScenario,
  generateScenarioImage,
  generateScenarioImagePrompt,
  generateUser,
  generateUserImage,
  generateUserImagePrompt,
  gmCardExportImageUrl,
  gmCardExportJsonUrl,
  getHardware,
  getMediaGenerationSettings,
  getModelSettings,
  getSillyTavernStatus,
  getProject,
  inspectCompatibility,
  listImageCandidates,
  listImageModels,
  listProjects,
  lorebookExportUrl,
  personaCardExportImageUrl,
  personaCardExportJsonUrl,
  restoreProject,
  syncProjectToSillyTavern,
  testMediaGenerationSettings,
  testModelSettingsConnection,
  testPromptPreview,
  updateCharacter,
  updateLoreEntry,
  updateMediaGenerationSettings,
  updateModelSettings,
  updateProject,
  updateGmCard,
  updateUserProfile,
  uploadImageModel,
  userExportUrl,
} from "./api";
import type {
  AssistantConnectionTest,
  Character,
  CompatibilityReport,
  GenerationTask,
  GMCardProfile,
  GeneratedImagePrompt,
  HardwareProfile,
  ImageCandidate,
  ImageShotFormat,
  ImageModelInventory,
  LoreEntry,
  LoreEntryPosition,
  MediaGenerationSettings,
  MediaGenerationSettingsTestResponse,
  MessageRole,
  ModelSettings,
  Project,
  ProjectCreateRequest,
  ProjectListItem,
  ProjectMode,
  ProjectScope,
  PromptPreviewResponse,
  TaskPromptProfile,
  UserProfile,
} from "./types";

type WorkspaceTab = "scenario" | "characters" | "lore" | "user" | "compatibility" | "settings";

const defaultProjectForm: ProjectCreateRequest = {
  name: "New Card Project",
  seed_sentence: "A mysterious gate opens beneath the city and calls only to you.",
  scenario_text: "",
  project_mode: "character",
  sample_character_target_count: 5,
  genre: "roleplay fantasy",
  tone: "mysterious and character-driven",
  lorebook_scan_depth: 4,
  lorebook_token_budget: 512,
  lorebook_recursive_scanning: false,
};

function joinTags(tags: string[]) {
  return tags.join(", ");
}

function parseTags(value: string) {
  return value
    .split(/[,\\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

type ImageOwnerType = "scenario" | "character" | "lore" | "user";
type PromptDraftField = "instruction" | "prompt" | "negative_prompt";

interface ImagePromptDraft {
  instruction: string;
  prompt: string;
  negative_prompt: string;
  style_profile: string;
}

const defaultPromptDraft: ImagePromptDraft = {
  instruction: "",
  prompt: "",
  negative_prompt: "",
  style_profile: "",
};

const allShotFormats: ImageShotFormat[] = ["portrait", "cowboy_shot", "fullbody_shot"];
const projectModes: ProjectMode[] = ["character", "game_master"];
const loreEntryPositions: LoreEntryPosition[] = ["before_char", "after_char", "before_examples", "after_examples"];
const messageRoles: MessageRole[] = ["system", "user", "assistant"];

function projectModeLabel(mode: ProjectMode) {
  return mode === "game_master" ? "Game Master" : "Character";
}

function imageSlotKey(ownerType: ImageOwnerType, ownerId: string, imageSlot: string) {
  return `${ownerType}:${ownerId}:${imageSlot}`;
}

function CharacterEditor({
  character,
  editable,
  loading,
  onSave,
  onDelete,
  onGeneratePrompt,
  onGenerateImage,
  onPromptDraftChange,
  onApproveCandidate,
  promptDrafts,
  candidatesBySlot,
  slotStatusBySlot,
}: {
  character: Character;
  editable: boolean;
  loading: boolean;
  onSave: (id: string, changes: Partial<Character>) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onGeneratePrompt: (id: string, format: ImageShotFormat) => Promise<void>;
  onGenerateImage: (id: string, format: ImageShotFormat) => Promise<void>;
  onPromptDraftChange: (id: string, format: ImageShotFormat, field: PromptDraftField, value: string) => void;
  onApproveCandidate: (id: string, format: ImageShotFormat, candidateId: string) => Promise<void>;
  promptDrafts: Record<ImageShotFormat, ImagePromptDraft>;
  candidatesBySlot: Record<ImageShotFormat, ImageCandidate[]>;
  slotStatusBySlot: Record<ImageShotFormat, string | null>;
}) {
  const [draft, setDraft] = useState(character);

  useEffect(() => {
    setDraft(character);
  }, [character]);

  return (
    <div className="panel" style={{ marginBottom: "1rem" }}>
      <div className="panel-header">
        <h3>{character.name}</h3>
        <div className="action-row">
          <button
            className="ghost-button"
            disabled={!editable || loading}
            onClick={() =>
              void onSave(character.id, {
                name: draft.name,
                description: draft.description,
                personality: draft.personality,
                scenario: draft.scenario,
                first_message: draft.first_message,
                example_dialogue: draft.example_dialogue,
                tags: draft.tags,
                creator_notes: draft.creator_notes,
                system_prompt: draft.system_prompt,
                post_history_instructions: draft.post_history_instructions,
                alternate_greetings: draft.alternate_greetings,
                creator: draft.creator,
                character_version: draft.character_version,
                character_note: draft.character_note,
                character_note_depth: draft.character_note_depth,
                character_note_role: draft.character_note_role,
                talkativeness: draft.talkativeness,
                appearance_summary: draft.appearance_summary,
                booru_character_name: draft.booru_character_name,
                booru_copyright: draft.booru_copyright,
              })
            }
          >
            Save
          </button>
          <button className="danger-button ghost-button" disabled={!editable || loading} onClick={() => void onDelete(character.id)}>
            Delete
          </button>
        </div>
      </div>
      <div className="project-grid">
        <label className="field">
          <span>Name</span>
          <input value={draft.name} disabled={!editable} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        </label>
        <label className="field">
          <span>Tags</span>
          <input
            value={joinTags(draft.tags)}
            disabled={!editable}
            onChange={(e) => setDraft({ ...draft, tags: parseTags(e.target.value) })}
          />
        </label>
        <label className="field">
          <span>Creator</span>
          <input value={draft.creator} disabled={!editable} onChange={(e) => setDraft({ ...draft, creator: e.target.value })} />
        </label>
        <label className="field">
          <span>Version</span>
          <input
            value={draft.character_version}
            disabled={!editable}
            onChange={(e) => setDraft({ ...draft, character_version: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Talkativeness</span>
          <input
            type="number"
            step="0.1"
            min={0}
            max={1}
            value={draft.talkativeness ?? ""}
            disabled={!editable}
            onChange={(e) =>
              setDraft({
                ...draft,
                talkativeness: e.target.value === "" ? null : Number(e.target.value),
              })
            }
          />
        </label>
        <label className="field scenario-field">
          <span>Description</span>
          <textarea rows={3} value={draft.description} disabled={!editable} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
        </label>
        <label className="field">
          <span>Personality</span>
          <textarea rows={3} value={draft.personality} disabled={!editable} onChange={(e) => setDraft({ ...draft, personality: e.target.value })} />
        </label>
        <label className="field">
          <span>Scenario</span>
          <textarea rows={3} value={draft.scenario} disabled={!editable} onChange={(e) => setDraft({ ...draft, scenario: e.target.value })} />
        </label>
        <label className="field scenario-field">
          <span>Appearance Summary</span>
          <textarea
            rows={3}
            value={draft.appearance_summary}
            disabled={!editable}
            onChange={(e) => setDraft({ ...draft, appearance_summary: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Booru Character Name</span>
          <input
            value={draft.booru_character_name}
            disabled={!editable}
            onChange={(e) => setDraft({ ...draft, booru_character_name: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Booru Copyright</span>
          <input
            value={draft.booru_copyright}
            disabled={!editable}
            onChange={(e) => setDraft({ ...draft, booru_copyright: e.target.value })}
          />
        </label>
        <label className="field">
          <span>First Message</span>
          <textarea rows={3} value={draft.first_message} disabled={!editable} onChange={(e) => setDraft({ ...draft, first_message: e.target.value })} />
        </label>
        <label className="field">
          <span>Example Dialogue</span>
          <textarea rows={3} value={draft.example_dialogue} disabled={!editable} onChange={(e) => setDraft({ ...draft, example_dialogue: e.target.value })} />
        </label>
        <label className="field">
          <span>Creator Notes</span>
          <textarea rows={3} value={draft.creator_notes} disabled={!editable} onChange={(e) => setDraft({ ...draft, creator_notes: e.target.value })} />
        </label>
        <label className="field">
          <span>System Prompt</span>
          <textarea rows={3} value={draft.system_prompt} disabled={!editable} onChange={(e) => setDraft({ ...draft, system_prompt: e.target.value })} />
        </label>
        <label className="field scenario-field">
          <span>Character Note</span>
          <textarea
            rows={3}
            value={draft.character_note}
            disabled={!editable}
            onChange={(e) => setDraft({ ...draft, character_note: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Note Depth</span>
          <input
            type="number"
            min={0}
            value={draft.character_note_depth}
            disabled={!editable}
            onChange={(e) => setDraft({ ...draft, character_note_depth: Number(e.target.value) || 0 })}
          />
        </label>
        <label className="field">
          <span>Note Role</span>
          <select
            value={draft.character_note_role}
            disabled={!editable}
            onChange={(e) => setDraft({ ...draft, character_note_role: e.target.value as MessageRole })}
          >
            {messageRoles.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Post-History Instructions</span>
          <textarea
            rows={3}
            value={draft.post_history_instructions}
            disabled={!editable}
            onChange={(e) => setDraft({ ...draft, post_history_instructions: e.target.value })}
          />
        </label>
        <label className="field scenario-field">
          <span>Alternate Greetings (comma separated)</span>
          <input
            value={joinTags(draft.alternate_greetings)}
            disabled={!editable}
            onChange={(e) => setDraft({ ...draft, alternate_greetings: parseTags(e.target.value) })}
          />
        </label>
      </div>
      {character.portrait_url || character.cowboy_shot_url || character.fullbody_shot_url ? (
        <div className="media-preview-grid" style={{ marginTop: "1rem" }}>
          {character.portrait_url ? <img src={character.portrait_url} alt={`${character.name} portrait`} /> : null}
          {character.cowboy_shot_url ? <img src={character.cowboy_shot_url} alt={`${character.name} cowboy shot`} /> : null}
          {character.fullbody_shot_url ? <img src={character.fullbody_shot_url} alt={`${character.name} full body`} /> : null}
        </div>
      ) : null}
      <div className="project-grid" style={{ marginTop: "1rem" }}>
        {allShotFormats.map((format) => {
          const draftForSlot = promptDrafts[format] ?? defaultPromptDraft;
          const candidates = candidatesBySlot[format] ?? [];
          const label =
            format === "portrait"
              ? "Portrait"
              : format === "cowboy_shot"
                ? "Cowboy Shot"
                : "Full Body";
          return (
            <div key={format} className="settings-card">
              {(() => {
                const slotStatus = slotStatusBySlot[format];
                const slotBusy = Boolean(slotStatus);
                return (
                  <>
              <div className="panel-header">
                <h3>{label} Prompt + Image</h3>
                {draftForSlot.style_profile ? <span className="badge muted">{draftForSlot.style_profile}</span> : null}
              </div>
              {slotStatus ? <p className="muted-text">{slotStatus}</p> : null}
              <div className="action-row" style={{ marginBottom: "0.8rem" }}>
                <button
                  className="ghost-button"
                  disabled={!editable || loading || slotBusy}
                  onClick={() => void onGeneratePrompt(character.id, format)}
                >
                  {slotStatus === "Generating prompt..." ? "Generating..." : "Generate Prompt"}
                </button>
                <button
                  className="primary-button"
                  disabled={!editable || loading || slotBusy || !draftForSlot.prompt.trim()}
                  onClick={() => void onGenerateImage(character.id, format)}
                >
                  {slotStatus === "Generating image..." ? "Generating..." : "Generate Image"}
                </button>
              </div>
              <label className="field">
                <span>Instruction (optional)</span>
                <input
                  value={draftForSlot.instruction}
                  disabled={!editable || loading || slotBusy}
                  onChange={(e) => onPromptDraftChange(character.id, format, "instruction", e.target.value)}
                />
              </label>
              <label className="field">
                <span>Prompt</span>
                <textarea
                  rows={4}
                  value={draftForSlot.prompt}
                  disabled={!editable || loading || slotBusy}
                  onChange={(e) => onPromptDraftChange(character.id, format, "prompt", e.target.value)}
                />
              </label>
              <label className="field">
                <span>Negative Prompt</span>
                <textarea
                  rows={3}
                  value={draftForSlot.negative_prompt}
                  disabled={!editable || loading || slotBusy}
                  onChange={(e) => onPromptDraftChange(character.id, format, "negative_prompt", e.target.value)}
                />
              </label>
              {candidates.length > 0 ? (
                <div className="variant-grid">
                  {candidates.map((candidate) => (
                    <div key={candidate.id} className="variant-card">
                      <img src={candidate.image_url} alt={`${character.name} ${label} candidate`} />
                      <div className="action-row">
                        <span className={`badge ${candidate.approved ? "success" : "muted"}`}>
                          {candidate.approved ? "Cover" : "Candidate"}
                        </span>
                        <button
                          className="ghost-button"
                          disabled={!editable || loading || slotBusy || candidate.approved}
                          onClick={() => void onApproveCandidate(character.id, format, candidate.id)}
                        >
                          Approve Cover
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted-text">No generated candidates yet.</p>
              )}
                  </>
                );
              })()}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function LoreEditor({
  lore,
  editable,
  loading,
  onSave,
  onDelete,
  onGeneratePrompt,
  onGenerateImage,
  onPromptDraftChange,
  onApproveCandidate,
  promptDraft,
  candidates,
  slotStatus,
}: {
  lore: LoreEntry;
  editable: boolean;
  loading: boolean;
  onSave: (id: string, changes: Partial<LoreEntry>) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onGeneratePrompt: (id: string) => Promise<void>;
  onGenerateImage: (id: string) => Promise<void>;
  onPromptDraftChange: (id: string, field: PromptDraftField, value: string) => void;
  onApproveCandidate: (id: string, candidateId: string) => Promise<void>;
  promptDraft: ImagePromptDraft;
  candidates: ImageCandidate[];
  slotStatus: string | null;
}) {
  const [draft, setDraft] = useState(lore);

  useEffect(() => {
    setDraft(lore);
  }, [lore]);

  return (
    <div className="panel" style={{ marginBottom: "1rem" }}>
      <div className="panel-header">
        <h3>{lore.name}</h3>
        <div className="action-row">
          <button
            className="ghost-button"
            disabled={!editable || loading}
            onClick={() =>
              void onSave(lore.id, {
                name: draft.name,
                keys: draft.keys,
                secondary_keys: draft.secondary_keys,
                content: draft.content,
                comment: draft.comment,
                enabled: draft.enabled,
                insertion_order: draft.insertion_order,
                position: draft.position,
                constant: draft.constant,
                selective_logic: draft.selective_logic,
                probability: draft.probability,
                case_sensitive: draft.case_sensitive,
                priority: draft.priority,
                scan_depth: draft.scan_depth,
                match_whole_words: draft.match_whole_words,
                group: draft.group,
                group_weight: draft.group_weight,
                prevent_recursion: draft.prevent_recursion,
                delay_until_recursion: draft.delay_until_recursion,
                character_filter_json: draft.character_filter_json,
                automation_id: draft.automation_id,
                role: draft.role,
                extensions_json: draft.extensions_json,
              })
            }
          >
            Save
          </button>
          <button className="danger-button ghost-button" disabled={!editable || loading} onClick={() => void onDelete(lore.id)}>
            Delete
          </button>
        </div>
      </div>
      <div className="project-grid">
        <label className="field">
          <span>Name</span>
          <input value={draft.name} disabled={!editable} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        </label>
        <label className="field">
          <span>Insertion Order</span>
          <input
            type="number"
            value={draft.insertion_order}
            disabled={!editable}
            onChange={(e) => setDraft({ ...draft, insertion_order: Number(e.target.value) })}
          />
        </label>
        <label className="field">
          <span>Keys</span>
          <input value={joinTags(draft.keys)} disabled={!editable} onChange={(e) => setDraft({ ...draft, keys: parseTags(e.target.value) })} />
        </label>
        <label className="field">
          <span>Secondary Keys</span>
          <input
            value={joinTags(draft.secondary_keys)}
            disabled={!editable}
            onChange={(e) => setDraft({ ...draft, secondary_keys: parseTags(e.target.value) })}
          />
        </label>
        <label className="field">
          <span>Position</span>
          <select value={draft.position} disabled={!editable} onChange={(e) => setDraft({ ...draft, position: e.target.value as LoreEntryPosition })}>
            {loreEntryPositions.map((position) => (
              <option key={position} value={position}>
                {position}
              </option>
            ))}
          </select>
        </label>
        <label className="toggle-row">
          <input type="checkbox" checked={draft.enabled} disabled={!editable} onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} />
          Enabled
        </label>
        <label className="field scenario-field">
          <span>Content</span>
          <textarea rows={4} value={draft.content} disabled={!editable} onChange={(e) => setDraft({ ...draft, content: e.target.value })} />
        </label>
        <label className="field scenario-field">
          <span>Comment</span>
          <textarea rows={2} value={draft.comment} disabled={!editable} onChange={(e) => setDraft({ ...draft, comment: e.target.value })} />
        </label>
      </div>
      <div className="settings-card" style={{ marginTop: "1rem" }}>
        <div className="panel-header">
          <h3>Advanced World Info</h3>
        </div>
        <div className="project-grid">
          <label className="field">
            <span>Priority</span>
            <input
              type="number"
              value={draft.priority}
              disabled={!editable}
              onChange={(e) => setDraft({ ...draft, priority: Number(e.target.value) || 0 })}
            />
          </label>
          <label className="field">
            <span>Probability</span>
            <input
              type="number"
              min={0}
              max={100}
              value={draft.probability}
              disabled={!editable}
              onChange={(e) => setDraft({ ...draft, probability: Number(e.target.value) || 0 })}
            />
          </label>
          <label className="field">
            <span>Selective Logic</span>
            <input
              type="number"
              value={draft.selective_logic}
              disabled={!editable}
              onChange={(e) => setDraft({ ...draft, selective_logic: Number(e.target.value) || 0 })}
            />
          </label>
          <label className="field">
            <span>Scan Depth</span>
            <input
              type="number"
              min={0}
              value={draft.scan_depth ?? ""}
              disabled={!editable}
              onChange={(e) => setDraft({ ...draft, scan_depth: e.target.value === "" ? null : Number(e.target.value) })}
            />
          </label>
          <label className="field">
            <span>Role</span>
            <select value={draft.role} disabled={!editable} onChange={(e) => setDraft({ ...draft, role: e.target.value as MessageRole })}>
              {messageRoles.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Group</span>
            <input value={draft.group} disabled={!editable} onChange={(e) => setDraft({ ...draft, group: e.target.value })} />
          </label>
          <label className="field">
            <span>Group Weight</span>
            <input
              type="number"
              value={draft.group_weight}
              disabled={!editable}
              onChange={(e) => setDraft({ ...draft, group_weight: Number(e.target.value) || 0 })}
            />
          </label>
          <label className="field">
            <span>Automation ID</span>
            <input value={draft.automation_id} disabled={!editable} onChange={(e) => setDraft({ ...draft, automation_id: e.target.value })} />
          </label>
          <label className="toggle-row">
            <input type="checkbox" checked={draft.constant} disabled={!editable} onChange={(e) => setDraft({ ...draft, constant: e.target.checked })} />
            Constant
          </label>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={draft.case_sensitive}
              disabled={!editable}
              onChange={(e) => setDraft({ ...draft, case_sensitive: e.target.checked })}
            />
            Case Sensitive
          </label>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={Boolean(draft.match_whole_words)}
              disabled={!editable}
              onChange={(e) => setDraft({ ...draft, match_whole_words: e.target.checked })}
            />
            Match Whole Words
          </label>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={draft.prevent_recursion}
              disabled={!editable}
              onChange={(e) => setDraft({ ...draft, prevent_recursion: e.target.checked })}
            />
            Prevent Recursion
          </label>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={draft.delay_until_recursion}
              disabled={!editable}
              onChange={(e) => setDraft({ ...draft, delay_until_recursion: e.target.checked })}
            />
            Delay Until Recursion
          </label>
          <label className="field scenario-field">
            <span>Character Filter JSON</span>
            <textarea
              rows={3}
              value={draft.character_filter_json}
              disabled={!editable}
              onChange={(e) => setDraft({ ...draft, character_filter_json: e.target.value })}
            />
          </label>
          <label className="field scenario-field">
            <span>Extensions JSON</span>
            <textarea
              rows={3}
              value={draft.extensions_json}
              disabled={!editable}
              onChange={(e) => setDraft({ ...draft, extensions_json: e.target.value })}
            />
          </label>
        </div>
      </div>
      {lore.image_url ? (
        <div style={{ marginTop: "1rem" }}>
          <img src={lore.image_url} alt={`${lore.name} lore`} style={{ maxWidth: 360, borderRadius: "16px" }} />
        </div>
      ) : null}
      <div className="settings-card" style={{ marginTop: "1rem" }}>
        <div className="panel-header">
          <h3>Lore Image Prompt + Candidates</h3>
          {promptDraft.style_profile ? <span className="badge muted">{promptDraft.style_profile}</span> : null}
        </div>
        {slotStatus ? <p className="muted-text">{slotStatus}</p> : null}
        <div className="action-row" style={{ marginBottom: "0.8rem" }}>
          <button className="ghost-button" disabled={!editable || loading || Boolean(slotStatus)} onClick={() => void onGeneratePrompt(lore.id)}>
            {slotStatus === "Generating prompt..." ? "Generating..." : "Generate Prompt"}
          </button>
          <button
            className="primary-button"
            disabled={!editable || loading || Boolean(slotStatus) || !promptDraft.prompt.trim()}
            onClick={() => void onGenerateImage(lore.id)}
          >
            {slotStatus === "Generating image..." ? "Generating..." : "Generate Image"}
          </button>
        </div>
        <label className="field">
          <span>Instruction (optional)</span>
          <input
            value={promptDraft.instruction}
            disabled={!editable || loading || Boolean(slotStatus)}
            onChange={(e) => onPromptDraftChange(lore.id, "instruction", e.target.value)}
          />
        </label>
        <label className="field">
          <span>Prompt</span>
          <textarea
            rows={4}
            value={promptDraft.prompt}
            disabled={!editable || loading || Boolean(slotStatus)}
            onChange={(e) => onPromptDraftChange(lore.id, "prompt", e.target.value)}
          />
        </label>
        <label className="field">
          <span>Negative Prompt</span>
          <textarea
            rows={3}
            value={promptDraft.negative_prompt}
            disabled={!editable || loading || Boolean(slotStatus)}
            onChange={(e) => onPromptDraftChange(lore.id, "negative_prompt", e.target.value)}
          />
        </label>
        {candidates.length > 0 ? (
          <div className="variant-grid">
            {candidates.map((candidate) => (
              <div key={candidate.id} className="variant-card">
                <img src={candidate.image_url} alt={`${lore.name} lore candidate`} />
                <div className="action-row">
                  <span className={`badge ${candidate.approved ? "success" : "muted"}`}>
                    {candidate.approved ? "Cover" : "Candidate"}
                  </span>
                  <button
                    className="ghost-button"
                    disabled={!editable || loading || Boolean(slotStatus) || candidate.approved}
                    onClick={() => void onApproveCandidate(lore.id, candidate.id)}
                  >
                    Approve Cover
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted-text">No generated candidates yet.</p>
        )}
      </div>
    </div>
  );
}

function App() {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [projectScope, setProjectScope] = useState<ProjectScope>("active");
  const [project, setProject] = useState<Project | null>(null);
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>("scenario");
  const [projectForm, setProjectForm] = useState<ProjectCreateRequest>(defaultProjectForm);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [imageSlotStatus, setImageSlotStatus] = useState<Record<string, string>>({});

  const [hardware, setHardware] = useState<HardwareProfile | null>(null);
  const [modelSettingsDraft, setModelSettingsDraft] = useState<ModelSettings | null>(null);
  const [mediaSettingsDraft, setMediaSettingsDraft] = useState<MediaGenerationSettings | null>(null);
  const [imageModels, setImageModels] = useState<ImageModelInventory | null>(null);
  const [connectionTest, setConnectionTest] = useState<AssistantConnectionTest | null>(null);
  const [mediaTest, setMediaTest] = useState<MediaGenerationSettingsTestResponse | null>(null);
  const [compatibilityReport, setCompatibilityReport] = useState<CompatibilityReport | null>(null);
  const [previewTask, setPreviewTask] = useState<GenerationTask>("scenario_generation");
  const [templateTask, setTemplateTask] = useState<GenerationTask>("scenario_generation");
  const [previewInstruction, setPreviewInstruction] = useState("");
  const [previewResult, setPreviewResult] = useState<PromptPreviewResponse | null>(null);
  const [gmCardInstruction, setGmCardInstruction] = useState("");
  const [promptDrafts, setPromptDrafts] = useState<Record<string, ImagePromptDraft>>({});
  const [candidateMap, setCandidateMap] = useState<Record<string, ImageCandidate[]>>({});

  const isProjectEditable = Boolean(project && !project.archived_at);

  function readPromptDraft(ownerType: ImageOwnerType, ownerId: string, imageSlot: string): ImagePromptDraft {
    return promptDrafts[imageSlotKey(ownerType, ownerId, imageSlot)] ?? defaultPromptDraft;
  }

  function writePromptDraft(ownerType: ImageOwnerType, ownerId: string, imageSlot: string, update: Partial<ImagePromptDraft>) {
    const key = imageSlotKey(ownerType, ownerId, imageSlot);
    setPromptDrafts((current) => ({
      ...current,
      [key]: {
        ...(current[key] ?? defaultPromptDraft),
        ...update,
      },
    }));
  }

  function readCandidates(ownerType: ImageOwnerType, ownerId: string, imageSlot: string): ImageCandidate[] {
    return candidateMap[imageSlotKey(ownerType, ownerId, imageSlot)] ?? [];
  }

  function readImageSlotStatus(ownerType: ImageOwnerType, ownerId: string, imageSlot: string) {
    return imageSlotStatus[imageSlotKey(ownerType, ownerId, imageSlot)] ?? null;
  }

  function setSlotStatus(ownerType: ImageOwnerType, ownerId: string, imageSlot: string, status: string | null) {
    const key = imageSlotKey(ownerType, ownerId, imageSlot);
    setImageSlotStatus((current) => {
      const next = { ...current };
      if (status) {
        next[key] = status;
      } else {
        delete next[key];
      }
      return next;
    });
  }

  function filenameFromDisposition(disposition: string | null, fallback: string) {
    if (!disposition) return fallback;
    const utfMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utfMatch?.[1]) {
      try {
        return decodeURIComponent(utfMatch[1].replace(/"/g, ""));
      } catch {
        return utfMatch[1].replace(/"/g, "");
      }
    }
    const asciiMatch = disposition.match(/filename="?([^";]+)"?/i);
    return asciiMatch?.[1] || fallback;
  }

  async function downloadExport(url: string, fallbackFilename: string) {
    setError(null);
    setNotice(`Preparing ${fallbackFilename}...`);
    try {
      const response = await fetch(url);
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || `Export failed with HTTP ${response.status}.`);
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filenameFromDisposition(response.headers.get("Content-Disposition"), fallbackFilename);
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
      setNotice(`Export downloaded: ${anchor.download}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setNotice(null);
    }
  }

  async function refreshCandidates(ownerType: ImageOwnerType, ownerId: string, imageSlot: string) {
    if (!project) return;
    const items = await listImageCandidates(project.id, {
      owner_type: ownerType,
      owner_id: ownerId,
      image_slot: imageSlot,
      limit: 18,
    });
    setCandidateMap((current) => ({
      ...current,
      [imageSlotKey(ownerType, ownerId, imageSlot)]: items,
    }));
  }

  function applyGeneratedPrompt(ownerType: ImageOwnerType, ownerId: string, payload: GeneratedImagePrompt) {
    writePromptDraft(ownerType, ownerId, payload.image_slot, {
      prompt: payload.prompt,
      negative_prompt: payload.negative_prompt,
      style_profile: payload.style_profile,
    });
  }

  function updateTemplateTaskProfile(task: GenerationTask, updates: Partial<TaskPromptProfile>) {
    if (!modelSettingsDraft) return;
    setModelSettingsDraft({
      ...modelSettingsDraft,
      task_profiles: {
        ...modelSettingsDraft.task_profiles,
        [task]: {
          ...modelSettingsDraft.task_profiles[task],
          ...updates,
        },
      },
    });
  }

  async function bootstrap() {
    setError(null);
    try {
      const [projectList, hw, modelSettings, mediaSettings, models] = await Promise.all([
        listProjects(projectScope),
        getHardware(),
        getModelSettings(),
        getMediaGenerationSettings(),
        listImageModels(),
      ]);
      setProjects(projectList);
      setHardware(hw);
      setModelSettingsDraft(modelSettings);
      const taskIds = modelSettings.task_catalog.map((item) => item.id);
      if (taskIds.length > 0) {
        if (!taskIds.includes(previewTask)) {
          setPreviewTask(taskIds[0]);
        }
        if (!taskIds.includes(templateTask)) {
          setTemplateTask(taskIds[0]);
        }
      }
      setMediaSettingsDraft(mediaSettings);
      setImageModels(models);
      if (!project && projectList[0]) {
        const detail = await getProject(projectList[0].id);
        setProject(detail);
      } else if (project) {
        const detail = await getProject(project.id);
        setProject(detail);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    void bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectScope]);

  useEffect(() => {
    setPromptDrafts({});
    setCandidateMap({});
    setCompatibilityReport(null);
  }, [project?.id]);

  useEffect(() => {
    if (!project) return;
    const activeProject = project;
    let cancelled = false;

    async function hydrateCandidatesForVisibleTab() {
      try {
        if (workspaceTab === "scenario") {
          await refreshCandidates("scenario", activeProject.id, "world");
          return;
        }
        if (workspaceTab === "characters") {
          for (const character of activeProject.characters) {
            for (const shot of allShotFormats) {
              await refreshCandidates("character", character.id, shot);
              if (cancelled) return;
            }
          }
          return;
        }
        if (workspaceTab === "lore") {
          for (const entry of activeProject.lore_entries) {
            await refreshCandidates("lore", entry.id, "lore");
            if (cancelled) return;
          }
          return;
        }
        if (workspaceTab === "user") {
          for (const shot of allShotFormats) {
            await refreshCandidates("user", activeProject.id, shot);
            if (cancelled) return;
          }
        }
      } catch {
        // Keep UI responsive even if candidate hydration fails.
      }
    }

    void hydrateCandidatesForVisibleTab();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id, workspaceTab, project?.characters.length, project?.lore_entries.length]);

  async function refreshProject(projectId: string) {
    const detail = await getProject(projectId);
    setProject(detail);
  }

  async function handleCreateProject() {
    setLoading(true);
    setError(null);
    try {
      const created = await createProject(projectForm);
      setProject(created);
      setProjectForm(defaultProjectForm);
      setNotice("Project created.");
      setProjects(await listProjects(projectScope));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectProject(projectId: string) {
    setLoading(true);
    setError(null);
    try {
      await refreshProject(projectId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveProjectCore() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
        const updated = await updateProject(project.id, {
          name: project.name,
          seed_sentence: project.seed_sentence,
          scenario_text: project.scenario_text,
          project_mode: project.project_mode,
          sample_character_target_count: project.sample_character_target_count,
          genre: project.genre,
          tone: project.tone,
          lorebook_scan_depth: project.lorebook_scan_depth,
          lorebook_token_budget: project.lorebook_token_budget,
          lorebook_recursive_scanning: project.lorebook_recursive_scanning,
        });
      setProject(updated);
      setNotice("Project saved.");
      setProjects(await listProjects(projectScope));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateAll() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const updated = await generateAll(project.id, {
        targetCount: project.project_mode === "game_master" ? project.sample_character_target_count : undefined,
      });
      setProject(updated);
      setNotice(
        updated.project_mode === "game_master"
          ? "Scenario, user persona, sample characters, lore, and GM card generated."
          : "Scenario, characters, lore, and user profile generated.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleLaunchSillyTavern() {
    setLoading(true);
    setError(null);
    try {
      const status = await getSillyTavernStatus();
      if (!status.enabled) {
        setNotice("SillyTavern integration is disabled.");
        return;
      }
      if (!status.healthy) {
        setNotice(status.warnings[0] ?? "SillyTavern is still starting. Try again in a moment.");
        return;
      }
      window.open(status.public_url, "_blank", "noopener,noreferrer");
      setNotice("SillyTavern opened in a new tab.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleSyncToSillyTavern() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const result = await syncProjectToSillyTavern(project.id);
      const warningSuffix = result.warnings.length > 0 ? ` ${result.warnings.join(" ")}` : "";
      setNotice(`Synced ${result.synced_files.length} files to SillyTavern.${warningSuffix}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleInspectCompatibility() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const report = await inspectCompatibility(project.id);
      setCompatibilityReport(report);
      setNotice(
        report.status === "blocked"
          ? `Compatibility check blocked sync with ${report.critical_count} critical issue(s).`
          : report.status === "warnings"
            ? `Compatibility check found ${report.warning_count} warning(s).`
            : "Compatibility check passed.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateScenario() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const updated = await generateScenario(project.id);
      setProject(updated);
      setNotice("Scenario generated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateCharacters() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const updated = await generateCharacters(project.id, {
        overwriteExisting: true,
        targetCount: project.project_mode === "game_master" ? project.sample_character_target_count : undefined,
      });
      setProject(updated);
      setNotice(
        updated.project_mode === "game_master"
          ? `Sample characters generated (${updated.characters.length}).`
          : "Characters generated.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateLore() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const updated = await generateLore(project.id, { overwriteExisting: true });
      setProject(updated);
      setNotice("Lore generated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateUser() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const updated = await generateUser(project.id);
      setProject(updated);
      setNotice("User profile generated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveGmCard(changes: Partial<GMCardProfile>) {
    if (!project) return;
    setError(null);
    try {
      const updatedProfile = await updateGmCard(project.id, changes);
      setProject({
        ...project,
        gm_card_profile: updatedProfile,
      });
      setNotice("GM card saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleGenerateGmCard() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const updated = await generateGmCard(project.id, gmCardInstruction);
      setProject(updated);
      setNotice("Game Master card generated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleAddCharacter() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
        await createCharacter(project.id, {
          name: "New Character",
          description: "",
          personality: "",
          scenario: project.scenario_text,
        first_message: "",
        example_dialogue: "",
        tags: [],
          creator_notes: "",
          system_prompt: "",
          post_history_instructions: "",
          alternate_greetings: [],
          creator: "",
          character_version: "",
          character_note: "",
          character_note_depth: 4,
          character_note_role: "system",
          talkativeness: null,
          appearance_summary: "",
          booru_character_name: "",
          booru_copyright: "",
        });
      await refreshProject(project.id);
      setNotice("Character added.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveCharacter(characterId: string, changes: Partial<Character>) {
    if (!project) return;
    setError(null);
    try {
      await updateCharacter(project.id, characterId, changes);
      await refreshProject(project.id);
      setNotice("Character saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleDeleteCharacter(characterId: string) {
    if (!project) return;
    setError(null);
    try {
      await deleteCharacter(project.id, characterId);
      await refreshProject(project.id);
      setNotice("Character deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleGenerateCharacterPrompt(characterId: string, format: ImageShotFormat) {
    if (!project) return;
    setError(null);
    setSlotStatus("character", characterId, format, "Generating prompt...");
    try {
      const draft = readPromptDraft("character", characterId, format);
      const generated = await generateCharacterImagePrompt(project.id, characterId, format, draft.instruction);
      applyGeneratedPrompt("character", characterId, generated);
      await refreshCandidates("character", characterId, format);
      setNotice(`Character ${format} prompt generated.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSlotStatus("character", characterId, format, null);
    }
  }

  function handleCharacterPromptDraftChange(
    characterId: string,
    format: ImageShotFormat,
    field: PromptDraftField,
    value: string,
  ) {
    writePromptDraft("character", characterId, format, { [field]: value });
  }

  async function handleGenerateCharacterImage(characterId: string, format: ImageShotFormat) {
    if (!project) return;
    setError(null);
    setSlotStatus("character", characterId, format, "Generating image...");
    setNotice(`Generating ${format} image...`);
    try {
      const draft = readPromptDraft("character", characterId, format);
      await generateCharacterImage(project.id, characterId, format, {
        instruction: draft.instruction,
        prompt: draft.prompt,
        negative_prompt: draft.negative_prompt,
      });
      await refreshProject(project.id);
      await refreshCandidates("character", characterId, format);
      setNotice(`Character ${format} image generated.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSlotStatus("character", characterId, format, null);
    }
  }

  async function handleApproveCharacterCandidate(characterId: string, format: ImageShotFormat, candidateId: string) {
    if (!project) return;
    setError(null);
    try {
      await approveImageCandidate(project.id, candidateId);
      await refreshProject(project.id);
      for (const shot of allShotFormats) {
        await refreshCandidates("character", characterId, shot);
      }
      setNotice(`Approved ${format} candidate as character cover.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleGenerateScenarioPrompt() {
    if (!project) return;
    setError(null);
    setSlotStatus("scenario", project.id, "world", "Generating prompt...");
    try {
      const draft = readPromptDraft("scenario", project.id, "world");
      const generated = await generateScenarioImagePrompt(project.id, draft.instruction);
      applyGeneratedPrompt("scenario", project.id, generated);
      await refreshCandidates("scenario", project.id, "world");
      setNotice("Scenario world prompt generated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSlotStatus("scenario", project.id, "world", null);
    }
  }

  function handleScenarioPromptDraftChange(field: PromptDraftField, value: string) {
    if (!project) return;
    writePromptDraft("scenario", project.id, "world", { [field]: value });
  }

  async function handleGenerateScenarioImage() {
    if (!project) return;
    setError(null);
    setSlotStatus("scenario", project.id, "world", "Generating image...");
    setNotice("Generating scenario world image...");
    try {
      const draft = readPromptDraft("scenario", project.id, "world");
      const updated = await generateScenarioImage(project.id, {
        instruction: draft.instruction,
        prompt: draft.prompt,
        negative_prompt: draft.negative_prompt,
      });
      setProject(updated);
      await refreshCandidates("scenario", project.id, "world");
      setNotice("Scenario world image generated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSlotStatus("scenario", project.id, "world", null);
    }
  }

  async function handleApproveScenarioCandidate(candidateId: string) {
    if (!project) return;
    setError(null);
    try {
      await approveImageCandidate(project.id, candidateId);
      await refreshProject(project.id);
      await refreshCandidates("scenario", project.id, "world");
      setNotice("Approved scenario world cover.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleAddLore() {
    if (!project) return;
    setError(null);
    try {
        await createLoreEntry(project.id, {
          name: "New Lore Entry",
          keys: [],
          secondary_keys: [],
          content: "",
        comment: "",
          enabled: true,
          insertion_order: 100,
          position: "after_char",
          constant: false,
          selective_logic: 0,
          probability: 100,
          case_sensitive: false,
          priority: 0,
          scan_depth: null,
          match_whole_words: false,
          group: "",
          group_weight: 100,
          prevent_recursion: true,
          delay_until_recursion: false,
          character_filter_json: "",
          automation_id: "",
          role: "system",
          extensions_json: "{}",
        });
      await refreshProject(project.id);
      setNotice("Lore entry added.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleSaveLore(loreId: string, changes: Partial<LoreEntry>) {
    if (!project) return;
    setError(null);
    try {
      await updateLoreEntry(project.id, loreId, changes);
      await refreshProject(project.id);
      setNotice("Lore entry saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleGenerateLorePrompt(loreId: string) {
    if (!project) return;
    setError(null);
    setSlotStatus("lore", loreId, "lore", "Generating prompt...");
    try {
      const draft = readPromptDraft("lore", loreId, "lore");
      const generated = await generateLoreImagePrompt(project.id, loreId, draft.instruction);
      applyGeneratedPrompt("lore", loreId, generated);
      await refreshCandidates("lore", loreId, "lore");
      setNotice("Lore prompt generated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSlotStatus("lore", loreId, "lore", null);
    }
  }

  function handleLorePromptDraftChange(loreId: string, field: PromptDraftField, value: string) {
    writePromptDraft("lore", loreId, "lore", { [field]: value });
  }

  async function handleGenerateLoreImage(loreId: string) {
    if (!project) return;
    setError(null);
    setSlotStatus("lore", loreId, "lore", "Generating image...");
    setNotice("Generating lore image...");
    try {
      const draft = readPromptDraft("lore", loreId, "lore");
      await generateLoreImage(project.id, loreId, {
        instruction: draft.instruction,
        prompt: draft.prompt,
        negative_prompt: draft.negative_prompt,
      });
      await refreshProject(project.id);
      await refreshCandidates("lore", loreId, "lore");
      setNotice("Lore image generated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSlotStatus("lore", loreId, "lore", null);
    }
  }

  async function handleApproveLoreCandidate(loreId: string, candidateId: string) {
    if (!project) return;
    setError(null);
    try {
      await approveImageCandidate(project.id, candidateId);
      await refreshProject(project.id);
      await refreshCandidates("lore", loreId, "lore");
      setNotice("Approved lore cover image.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleDeleteLore(loreId: string) {
    if (!project) return;
    setError(null);
    try {
      await deleteLoreEntry(project.id, loreId);
      await refreshProject(project.id);
      setNotice("Lore entry deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleSaveUserProfile(changes: Partial<UserProfile>) {
    if (!project) return;
    setError(null);
    try {
      await updateUserProfile(project.id, changes);
      await refreshProject(project.id);
      setNotice("User profile saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleGenerateUserPrompt(format: ImageShotFormat) {
    if (!project) return;
    setError(null);
    setSlotStatus("user", project.id, format, "Generating prompt...");
    try {
      const draft = readPromptDraft("user", project.id, format);
      const generated = await generateUserImagePrompt(project.id, format, draft.instruction);
      applyGeneratedPrompt("user", project.id, generated);
      await refreshCandidates("user", project.id, format);
      setNotice(`User ${format} prompt generated.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSlotStatus("user", project.id, format, null);
    }
  }

  function handleUserPromptDraftChange(format: ImageShotFormat, field: PromptDraftField, value: string) {
    if (!project) return;
    writePromptDraft("user", project.id, format, { [field]: value });
  }

  async function handleGenerateUserImage(format: ImageShotFormat) {
    if (!project) return;
    setError(null);
    setSlotStatus("user", project.id, format, "Generating image...");
    setNotice(`Generating user ${format} image...`);
    try {
      const draft = readPromptDraft("user", project.id, format);
      await generateUserImage(project.id, format, {
        instruction: draft.instruction,
        prompt: draft.prompt,
        negative_prompt: draft.negative_prompt,
      });
      await refreshProject(project.id);
      await refreshCandidates("user", project.id, format);
      setNotice(`User ${format} image generated.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSlotStatus("user", project.id, format, null);
    }
  }

  async function handleApproveUserCandidate(format: ImageShotFormat, candidateId: string) {
    if (!project) return;
    setError(null);
    try {
      await approveImageCandidate(project.id, candidateId);
      await refreshProject(project.id);
      for (const shot of allShotFormats) {
        await refreshCandidates("user", project.id, shot);
      }
      setNotice(`Approved ${format} as user persona cover.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleArchiveOrRestoreProject() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const updated = project.archived_at ? await restoreProject(project.id) : await archiveProject(project.id);
      setProject(updated);
      setNotice(project.archived_at ? "Project restored." : "Project archived.");
      setProjects(await listProjects(projectScope));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteProject() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      await deleteProject(project.id);
      setProject(null);
      setProjects(await listProjects(projectScope));
      setNotice("Project deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveModelSettings() {
    if (!modelSettingsDraft) return;
    setLoading(true);
    setError(null);
    try {
      const updated = await updateModelSettings({
        runtime: modelSettingsDraft.runtime,
        generation_defaults: modelSettingsDraft.generation_defaults,
        task_profiles: modelSettingsDraft.task_profiles,
      });
      setModelSettingsDraft(updated);
      setNotice("Model settings saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleTestModelSettings() {
    if (!modelSettingsDraft) return;
    setLoading(true);
    setError(null);
    try {
      const result = await testModelSettingsConnection({
        runtime: modelSettingsDraft.runtime,
        generation_defaults: modelSettingsDraft.generation_defaults,
        task_profiles: modelSettingsDraft.task_profiles,
      });
      setConnectionTest(result);
      setNotice("Runtime connection tested.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handlePreviewPrompt() {
    if (!project) return;
    setLoading(true);
    setError(null);
    try {
      const result = await testPromptPreview({
        task: previewTask,
        project_id: project.id,
        instruction: previewInstruction,
        run_model: false,
      });
      setPreviewResult(result);
      setNotice("Prompt preview rendered.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  function handleClearPromptPreviewContext() {
    setPreviewInstruction("");
    setPreviewResult(null);
    setNotice("LLM prompt preview context cleared.");
  }

  async function handleSaveMediaSettings() {
    if (!mediaSettingsDraft) return;
    setLoading(true);
    setError(null);
    try {
      const updated = await updateMediaGenerationSettings(mediaSettingsDraft);
      setMediaSettingsDraft(updated);
      setImageModels(await listImageModels());
      setNotice("Image generation settings saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleTestMediaSettings() {
    if (!mediaSettingsDraft) return;
    setLoading(true);
    setError(null);
    try {
      const result = await testMediaGenerationSettings(mediaSettingsDraft);
      setMediaTest(result);
      setNotice("Image settings tested.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleRefreshImageModels() {
    setLoading(true);
    setError(null);
    try {
      const models = await listImageModels();
      setImageModels(models);
      setNotice(`Image model inventory refreshed (${models.models.length} found).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleUploadImageModel(file: File | null) {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const uploaded = await uploadImageModel(file, { set_default: true });
      setMediaSettingsDraft(uploaded.settings);
      setImageModels(uploaded.inventory);
      setNotice(`Model uploaded: ${uploaded.uploaded_model.label}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  const latestRuns = useMemo(() => project?.generation_runs.slice(0, 5) ?? [], [project]);
  const scenarioWorldDraft = project ? readPromptDraft("scenario", project.id, "world") : defaultPromptDraft;
  const scenarioWorldCandidates = project ? readCandidates("scenario", project.id, "world") : [];
  const scenarioWorldStatus = project ? readImageSlotStatus("scenario", project.id, "world") : null;
  const selectedTaskProfile = modelSettingsDraft ? modelSettingsDraft.task_profiles[templateTask] : null;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <section className="brand-card">
          <p className="eyebrow">SillyTavern</p>
          <h1>Card Creator Reboot</h1>
          <p className="muted-text">Create scenario, characters, lorebook, and user persona with local LLM + image generation.</p>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Create Project</h2>
            <button className="primary-button" disabled={loading} onClick={() => void handleCreateProject()}>
              {loading ? "Working..." : "Create"}
            </button>
          </div>
          <label className="field">
            <span>Name</span>
            <input value={projectForm.name} onChange={(e) => setProjectForm({ ...projectForm, name: e.target.value })} />
          </label>
          <label className="field">
            <span>Seed Sentence</span>
            <textarea
              rows={3}
              value={projectForm.seed_sentence}
              onChange={(e) => setProjectForm({ ...projectForm, seed_sentence: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Genre</span>
            <input value={projectForm.genre} onChange={(e) => setProjectForm({ ...projectForm, genre: e.target.value })} />
          </label>
          <label className="field">
            <span>Tone</span>
            <input value={projectForm.tone} onChange={(e) => setProjectForm({ ...projectForm, tone: e.target.value })} />
          </label>
          <label className="field">
            <span>Mode</span>
            <select
              value={projectForm.project_mode}
              onChange={(e) => setProjectForm({ ...projectForm, project_mode: e.target.value as ProjectMode })}
            >
              {projectModes.map((mode) => (
                <option key={mode} value={mode}>
                  {projectModeLabel(mode)}
                </option>
              ))}
            </select>
          </label>
          {projectForm.project_mode === "game_master" ? (
            <label className="field">
              <span>GM Sample Count</span>
              <input
                type="number"
                min={1}
                max={10}
                value={projectForm.sample_character_target_count}
                onChange={(e) =>
                  setProjectForm({
                    ...projectForm,
                    sample_character_target_count: Math.max(1, Math.min(10, Number(e.target.value) || 1)),
                  })
                }
              />
            </label>
          ) : null}
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Projects</h2>
            <select value={projectScope} onChange={(e) => setProjectScope(e.target.value as ProjectScope)}>
              <option value="active">active</option>
              <option value="archived">archived</option>
              <option value="all">all</option>
            </select>
          </div>
          <div className="project-list">
            {projects.map((item) => (
              <button
                key={item.id}
                className={`project-chip ${project?.id === item.id ? "active" : ""}`}
                onClick={() => void handleSelectProject(item.id)}
                >
                  <strong>{item.name}</strong>
                  <span>{item.character_count} chars • {item.lore_count} lore</span>
                  <span className="mini-badge">{projectModeLabel(item.project_mode)}</span>
                </button>
              ))}
            {projects.length === 0 ? <p className="muted-text">No projects for this scope.</p> : null}
          </div>
        </section>

        {notice ? <section className="alert info">{notice}</section> : null}
        {error ? <section className="alert error">{error}</section> : null}
      </aside>

      <main className="workspace">
        <section className="hero-panel">
          <div>
            <p className="eyebrow">Workflow</p>
            <h2>{project ? project.name : "No project selected"}</h2>
            <p className="lede">
              {project
                ? project.project_mode === "game_master"
                  ? "Build a GM scenario card with sample characters, lore, and persona support assets."
                  : "Use Generate All for first draft, then refine each tab and export SillyTavern assets."
                : "Create or select a project to start."}
            </p>
            {project ? (
              <div className="action-row">
                <button className="primary-button" disabled={!isProjectEditable || loading} onClick={() => void handleGenerateAll()}>
                  Generate All
                </button>
                <button className="ghost-button" disabled={loading} onClick={() => void handleLaunchSillyTavern()}>
                  Launch SillyTavern
                </button>
                <button className="ghost-button" disabled={loading} onClick={() => void handleSyncToSillyTavern()}>
                  Sync to SillyTavern
                </button>
                <button className="ghost-button" disabled={!isProjectEditable || loading} onClick={() => void handleSaveProjectCore()}>
                  Save Core
                </button>
                <button className="ghost-button" disabled={loading} onClick={() => void handleArchiveOrRestoreProject()}>
                  {project.archived_at ? "Restore" : "Archive"}
                </button>
                <button className="danger-button ghost-button" disabled={loading} onClick={() => void handleDeleteProject()}>
                  Delete
                </button>
              </div>
            ) : null}
          </div>
          <div className="hardware-card">
            <h3>Runtime Snapshot</h3>
            {hardware ? (
              <>
                <p className="muted-text">{hardware.gpu_name ?? "No GPU detected"} • CUDA {hardware.cuda_available ? "ready" : "off"}</p>
                <p className="muted-text">{hardware.support_tier}</p>
              </>
            ) : (
              <p className="muted-text">Loading hardware profile…</p>
            )}
          </div>
        </section>

        {project ? (
          <>
            <section className="panel">
              <div className="tab-row">
                {(["scenario", "user", "characters", "lore", "compatibility", "settings"] as const).map((tab) => (
                  <button key={tab} className={`tab-button ${workspaceTab === tab ? "active" : ""}`} onClick={() => setWorkspaceTab(tab)}>
                    {tab}
                  </button>
                ))}
              </div>
            </section>

            {workspaceTab === "scenario" ? (
              <section className="panel">
                <div className="panel-header">
                  <h2>Scenario</h2>
                  <div className="action-row">
                    <button className="ghost-button" disabled={!isProjectEditable || loading || Boolean(scenarioWorldStatus)} onClick={() => void handleGenerateScenarioPrompt()}>
                      {scenarioWorldStatus === "Generating prompt..." ? "Generating..." : "Generate World Prompt"}
                    </button>
                    <button className="ghost-button" disabled={!isProjectEditable || loading || Boolean(scenarioWorldStatus) || !scenarioWorldDraft.prompt.trim()} onClick={() => void handleGenerateScenarioImage()}>
                      {scenarioWorldStatus === "Generating image..." ? "Generating..." : "Generate World Image"}
                    </button>
                    <button className="ghost-button" disabled={!isProjectEditable || loading} onClick={() => void handleGenerateScenario()}>
                      Regenerate Scenario
                    </button>
                  </div>
                </div>
                {scenarioWorldStatus ? <p className="muted-text">{scenarioWorldStatus}</p> : null}
                <div className="project-grid">
                  <label className="field">
                    <span>Name</span>
                    <input
                      disabled={!isProjectEditable}
                      value={project.name}
                      onChange={(e) => setProject({ ...project, name: e.target.value })}
                    />
                  </label>
                  <label className="field">
                    <span>Project Mode</span>
                    <select
                      disabled={!isProjectEditable}
                      value={project.project_mode}
                      onChange={(e) => setProject({ ...project, project_mode: e.target.value as ProjectMode })}
                    >
                      {projectModes.map((mode) => (
                        <option key={mode} value={mode}>
                          {projectModeLabel(mode)}
                        </option>
                      ))}
                    </select>
                  </label>
                  {project.project_mode === "game_master" ? (
                    <label className="field">
                      <span>GM Sample Count</span>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        disabled={!isProjectEditable}
                        value={project.sample_character_target_count}
                        onChange={(e) =>
                          setProject({
                            ...project,
                            sample_character_target_count: Math.max(1, Math.min(10, Number(e.target.value) || 1)),
                          })
                        }
                      />
                    </label>
                  ) : null}
                  <label className="field">
                    <span>Genre</span>
                    <input
                      disabled={!isProjectEditable}
                      value={project.genre}
                      onChange={(e) => setProject({ ...project, genre: e.target.value })}
                    />
                  </label>
                  <label className="field">
                    <span>Tone</span>
                    <input
                      disabled={!isProjectEditable}
                      value={project.tone}
                      onChange={(e) => setProject({ ...project, tone: e.target.value })}
                    />
                  </label>
                  <label className="field">
                    <span>Lorebook Scan Depth</span>
                    <input
                      type="number"
                      min={0}
                      disabled={!isProjectEditable}
                      value={project.lorebook_scan_depth}
                      onChange={(e) => setProject({ ...project, lorebook_scan_depth: Number(e.target.value) || 0 })}
                    />
                  </label>
                  <label className="field">
                    <span>Lorebook Token Budget</span>
                    <input
                      type="number"
                      min={0}
                      disabled={!isProjectEditable}
                      value={project.lorebook_token_budget}
                      onChange={(e) => setProject({ ...project, lorebook_token_budget: Number(e.target.value) || 0 })}
                    />
                  </label>
                  <label className="toggle-row">
                    <input
                      type="checkbox"
                      checked={project.lorebook_recursive_scanning}
                      disabled={!isProjectEditable}
                      onChange={(e) => setProject({ ...project, lorebook_recursive_scanning: e.target.checked })}
                    />
                    Recursive Lorebook Scanning
                  </label>
                  <label className="field scenario-field">
                    <span>Seed Sentence</span>
                    <textarea
                      rows={3}
                      disabled={!isProjectEditable}
                      value={project.seed_sentence}
                      onChange={(e) => setProject({ ...project, seed_sentence: e.target.value })}
                    />
                  </label>
                  <label className="field scenario-field">
                    <span>Scenario Text</span>
                    <textarea
                      rows={10}
                      disabled={!isProjectEditable}
                      value={project.scenario_text}
                      onChange={(e) => setProject({ ...project, scenario_text: e.target.value })}
                    />
                  </label>
                  <label className="field scenario-field">
                    <span>World Image Prompt Instruction (optional)</span>
                    <input
                      disabled={!isProjectEditable || loading || Boolean(scenarioWorldStatus)}
                      value={scenarioWorldDraft.instruction}
                      onChange={(e) => handleScenarioPromptDraftChange("instruction", e.target.value)}
                    />
                  </label>
                  <label className="field scenario-field">
                    <span>World Image Prompt</span>
                    <textarea
                      rows={4}
                      disabled={!isProjectEditable || loading || Boolean(scenarioWorldStatus)}
                      value={scenarioWorldDraft.prompt}
                      onChange={(e) => handleScenarioPromptDraftChange("prompt", e.target.value)}
                    />
                  </label>
                  <label className="field scenario-field">
                    <span>World Negative Prompt</span>
                    <textarea
                      rows={3}
                      disabled={!isProjectEditable || loading || Boolean(scenarioWorldStatus)}
                      value={scenarioWorldDraft.negative_prompt}
                      onChange={(e) => handleScenarioPromptDraftChange("negative_prompt", e.target.value)}
                    />
                  </label>
                </div>
                {scenarioWorldDraft.style_profile ? <p className="muted-text">Style profile: {scenarioWorldDraft.style_profile}</p> : null}
                {project.scenario_world_image_url ? (
                  <div style={{ marginTop: "1rem" }}>
                    <img src={project.scenario_world_image_url} alt={`${project.name} world`} style={{ width: "100%", borderRadius: "16px" }} />
                  </div>
                ) : null}
                <div className="variant-grid" style={{ marginTop: "1rem" }}>
                  {scenarioWorldCandidates.map((candidate) => (
                    <div key={candidate.id} className="variant-card">
                      <img src={candidate.image_url} alt={`${project.name} world candidate`} />
                      <div className="action-row">
                        <span className={`badge ${candidate.approved ? "success" : "muted"}`}>
                          {candidate.approved ? "Cover" : "Candidate"}
                        </span>
                        <button
                          className="ghost-button"
                          disabled={!isProjectEditable || loading || candidate.approved}
                          onClick={() => void handleApproveScenarioCandidate(candidate.id)}
                        >
                          Approve Cover
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
                {project.project_mode === "game_master" ? (
                  <div className="settings-card" style={{ marginTop: "1rem" }}>
                    <div className="panel-header">
                      <h3>Game Master Card</h3>
                      <div className="action-row">
                        <button
                          className="ghost-button"
                          disabled={!isProjectEditable || loading || Boolean(scenarioWorldStatus)}
                          onClick={() =>
                            void handleSaveGmCard({
                              ...project.gm_card_profile,
                            })
                          }
                        >
                          Save GM Card
                        </button>
                        <button className="ghost-button" disabled={!isProjectEditable || loading} onClick={() => void handleGenerateGmCard()}>
                          Generate GM Card
                        </button>
                      </div>
                    </div>
                    <div className="project-grid">
                      <label className="field">
                        <span>Name</span>
                        <input
                          disabled={!isProjectEditable}
                          value={project.gm_card_profile.name}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: { ...project.gm_card_profile, name: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Tags</span>
                        <input
                          disabled={!isProjectEditable}
                          value={joinTags(project.gm_card_profile.tags)}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: { ...project.gm_card_profile, tags: parseTags(e.target.value) },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Creator</span>
                        <input
                          disabled={!isProjectEditable}
                          value={project.gm_card_profile.creator}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: { ...project.gm_card_profile, creator: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Version</span>
                        <input
                          disabled={!isProjectEditable}
                          value={project.gm_card_profile.character_version}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: { ...project.gm_card_profile, character_version: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Talkativeness</span>
                        <input
                          type="number"
                          step="0.1"
                          min={0}
                          max={1}
                          disabled={!isProjectEditable}
                          value={project.gm_card_profile.talkativeness ?? ""}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: {
                                ...project.gm_card_profile,
                                talkativeness: e.target.value === "" ? null : Number(e.target.value),
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field scenario-field">
                        <span>Description</span>
                        <textarea
                          rows={3}
                          disabled={!isProjectEditable}
                          value={project.gm_card_profile.description}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: { ...project.gm_card_profile, description: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Personality</span>
                        <textarea
                          rows={3}
                          disabled={!isProjectEditable}
                          value={project.gm_card_profile.personality}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: { ...project.gm_card_profile, personality: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>First Message</span>
                        <textarea
                          rows={3}
                          disabled={!isProjectEditable}
                          value={project.gm_card_profile.first_message}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: { ...project.gm_card_profile, first_message: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="field scenario-field">
                        <span>Scenario</span>
                        <textarea
                          rows={4}
                          disabled={!isProjectEditable}
                          value={project.gm_card_profile.scenario}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: { ...project.gm_card_profile, scenario: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="field scenario-field">
                        <span>Example Dialogue</span>
                        <textarea
                          rows={4}
                          disabled={!isProjectEditable}
                          value={project.gm_card_profile.example_dialogue}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: { ...project.gm_card_profile, example_dialogue: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Creator Notes</span>
                        <textarea
                          rows={3}
                          disabled={!isProjectEditable}
                          value={project.gm_card_profile.creator_notes}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: { ...project.gm_card_profile, creator_notes: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>System Prompt</span>
                        <textarea
                          rows={3}
                          disabled={!isProjectEditable}
                          value={project.gm_card_profile.system_prompt}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: { ...project.gm_card_profile, system_prompt: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="field scenario-field">
                        <span>Character Note</span>
                        <textarea
                          rows={3}
                          disabled={!isProjectEditable}
                          value={project.gm_card_profile.character_note}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: { ...project.gm_card_profile, character_note: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Note Depth</span>
                        <input
                          type="number"
                          min={0}
                          disabled={!isProjectEditable}
                          value={project.gm_card_profile.character_note_depth}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: {
                                ...project.gm_card_profile,
                                character_note_depth: Number(e.target.value) || 0,
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Note Role</span>
                        <select
                          disabled={!isProjectEditable}
                          value={project.gm_card_profile.character_note_role}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: { ...project.gm_card_profile, character_note_role: e.target.value as MessageRole },
                            })
                          }
                        >
                          {messageRoles.map((role) => (
                            <option key={role} value={role}>
                              {role}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field">
                        <span>Post-History Instructions</span>
                        <textarea
                          rows={3}
                          disabled={!isProjectEditable}
                          value={project.gm_card_profile.post_history_instructions}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: { ...project.gm_card_profile, post_history_instructions: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Alternate Greetings</span>
                        <input
                          disabled={!isProjectEditable}
                          value={joinTags(project.gm_card_profile.alternate_greetings)}
                          onChange={(e) =>
                            setProject({
                              ...project,
                              gm_card_profile: { ...project.gm_card_profile, alternate_greetings: parseTags(e.target.value) },
                            })
                          }
                        />
                      </label>
                      <label className="field scenario-field">
                        <span>Generation Instruction (optional)</span>
                        <input
                          disabled={!isProjectEditable || loading}
                          value={gmCardInstruction}
                          onChange={(e) => setGmCardInstruction(e.target.value)}
                        />
                      </label>
                    </div>
                    <div className="panel-header" style={{ marginTop: "1rem" }}>
                      <h3>SillyTavern GM Card Export</h3>
                      <button className="ghost-button" disabled={loading} onClick={() => void handleSyncToSillyTavern()}>
                        Sync to SillyTavern
                      </button>
                    </div>
                    <p className="muted-text">
                      Exports the final Game Master scenario card as a SillyTavern-compatible character card, embedding the shared
                      lorebook and GM-oriented behavior fields alongside the scenario, opening message, example dialogue, system prompt,
                      and post-history instructions.
                    </p>
                    <div className="project-list">
                      <div className="export-card">
                        <strong>{project.gm_card_profile.name || `${project.name} GM`}</strong>
                        <div className="action-row">
                          <button className="ghost-button" onClick={() => void downloadExport(gmCardExportJsonUrl(project.id), `${project.name}-gm-card.json`)}>
                            JSON
                          </button>
                          <button className="ghost-button" onClick={() => void downloadExport(gmCardExportImageUrl(project.id, "png"), `${project.name}-gm-card.png`)}>
                            PNG
                          </button>
                          <button className="ghost-button" onClick={() => void downloadExport(gmCardExportImageUrl(project.id, "webp"), `${project.name}-gm-card.webp`)}>
                            WEBP
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="settings-card" style={{ marginTop: "1rem" }}>
                    <div className="panel-header">
                      <h3>Scenario Export</h3>
                    </div>
                    <p className="muted-text">
                      In character mode, the scenario is exported inside each SillyTavern character card on the Characters tab rather
                      than as a standalone scenario file.
                    </p>
                  </div>
                )}
              </section>
            ) : null}

            {workspaceTab === "characters" ? (
              <>
                <section className="panel">
                  <div className="panel-header">
                    <h2>{project.project_mode === "game_master" ? "Sample Customers" : "Characters"}</h2>
                    <div className="action-row">
                      {project.project_mode === "game_master" ? (
                        <label className="field compact" style={{ marginBottom: 0, minWidth: 160 }}>
                          <span>Target Count</span>
                          <input
                            type="number"
                            min={1}
                            max={10}
                            disabled={!isProjectEditable || loading}
                            value={project.sample_character_target_count}
                            onChange={(e) =>
                              setProject({
                                ...project,
                                sample_character_target_count: Math.max(1, Math.min(10, Number(e.target.value) || 1)),
                              })
                            }
                          />
                        </label>
                      ) : null}
                      <button className="ghost-button" disabled={!isProjectEditable || loading} onClick={() => void handleGenerateCharacters()}>
                        {project.project_mode === "game_master" ? "Regenerate Samples" : "Regenerate Characters"}
                      </button>
                      <button className="primary-button" disabled={!isProjectEditable || loading} onClick={() => void handleAddCharacter()}>
                        Add Character
                      </button>
                    </div>
                  </div>
                  {project.project_mode === "game_master" ? (
                    <p className="muted-text">
                      In Game Master mode, these cards are sample NPC/customer references for the main GM scenario card.
                    </p>
                  ) : null}
                </section>
                {project.characters.length === 0 ? (
                  <section className="panel">
                    <p className="muted-text">
                      {project.project_mode === "game_master" ? "No sample characters yet." : "No characters yet."}
                    </p>
                  </section>
                ) : null}
                {project.characters.map((character) => (
                  <CharacterEditor
                    key={character.id}
                    character={character}
                    editable={isProjectEditable}
                    loading={loading}
                    onSave={handleSaveCharacter}
                    onDelete={handleDeleteCharacter}
                    onGeneratePrompt={handleGenerateCharacterPrompt}
                    onGenerateImage={handleGenerateCharacterImage}
                    onPromptDraftChange={handleCharacterPromptDraftChange}
                    onApproveCandidate={handleApproveCharacterCandidate}
                    promptDrafts={{
                      portrait: readPromptDraft("character", character.id, "portrait"),
                      cowboy_shot: readPromptDraft("character", character.id, "cowboy_shot"),
                      fullbody_shot: readPromptDraft("character", character.id, "fullbody_shot"),
                    }}
                    candidatesBySlot={{
                      portrait: readCandidates("character", character.id, "portrait"),
                      cowboy_shot: readCandidates("character", character.id, "cowboy_shot"),
                      fullbody_shot: readCandidates("character", character.id, "fullbody_shot"),
                    }}
                    slotStatusBySlot={{
                      portrait: readImageSlotStatus("character", character.id, "portrait"),
                      cowboy_shot: readImageSlotStatus("character", character.id, "cowboy_shot"),
                      fullbody_shot: readImageSlotStatus("character", character.id, "fullbody_shot"),
                    }}
                  />
                ))}
                {project.characters.length > 0 ? (
                  <section className="panel">
                    <div className="panel-header">
                      <h2>Exports</h2>
                      <button className="ghost-button" disabled={loading} onClick={() => void handleSyncToSillyTavern()}>
                        Sync to SillyTavern
                      </button>
                    </div>
                    <div className="project-list">
                      {project.characters.map((character) => (
                        <div key={character.id} className="export-card">
                          <strong>{character.name}</strong>
                          <div className="action-row">
                            <button className="ghost-button" onClick={() => void downloadExport(characterExportJsonUrl(project.id, character.id), `${character.name}-card.json`)}>
                              JSON
                            </button>
                            <button className="ghost-button" onClick={() => void downloadExport(characterExportImageUrl(project.id, character.id, "png"), `${character.name}-card.png`)}>
                              PNG
                            </button>
                            <button className="ghost-button" onClick={() => void downloadExport(characterExportImageUrl(project.id, character.id, "webp"), `${character.name}-card.webp`)}>
                              WEBP
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                ) : null}
              </>
            ) : null}

            {workspaceTab === "lore" ? (
              <>
                <section className="panel">
                  <div className="panel-header">
                    <h2>Lore/World</h2>
                    <div className="action-row">
                      <button className="ghost-button" disabled={!isProjectEditable || loading} onClick={() => void handleGenerateLore()}>
                        Regenerate Lore
                      </button>
                      <button className="primary-button" disabled={!isProjectEditable || loading} onClick={() => void handleAddLore()}>
                        Add Entry
                      </button>
                    </div>
                  </div>
                  <div className="project-grid">
                    <label className="field">
                      <span>Lorebook Scan Depth</span>
                      <input
                        type="number"
                        min={0}
                        disabled={!isProjectEditable}
                        value={project.lorebook_scan_depth}
                        onChange={(e) => setProject({ ...project, lorebook_scan_depth: Number(e.target.value) || 0 })}
                      />
                    </label>
                    <label className="field">
                      <span>Lorebook Token Budget</span>
                      <input
                        type="number"
                        min={0}
                        disabled={!isProjectEditable}
                        value={project.lorebook_token_budget}
                        onChange={(e) => setProject({ ...project, lorebook_token_budget: Number(e.target.value) || 0 })}
                      />
                    </label>
                    <label className="toggle-row">
                      <input
                        type="checkbox"
                        checked={project.lorebook_recursive_scanning}
                        disabled={!isProjectEditable}
                        onChange={(e) => setProject({ ...project, lorebook_recursive_scanning: e.target.checked })}
                      />
                      Recursive Scanning
                    </label>
                  </div>
                  <p className="muted-text">
                    These lorebook settings are saved with the project and reused for both standalone lorebook export and the embedded GM
                    card `character_book`.
                  </p>
                </section>
                <section className="panel">
                  <div className="panel-header">
                    <h2>Lorebook Export</h2>
                    <button className="ghost-button" disabled={loading} onClick={() => void handleSyncToSillyTavern()}>
                      Sync to SillyTavern
                    </button>
                  </div>
                  <p className="muted-text">
                    Exports the project world info as a SillyTavern lorebook JSON file that can be linked to a character, persona, or chat.
                  </p>
                  <div className="project-list">
                    <div className="export-card">
                      <strong>{project.name} Lorebook</strong>
                      <div className="action-row">
                        <button className="ghost-button" onClick={() => void downloadExport(lorebookExportUrl(project.id), `${project.name}-lorebook.json`)}>
                          JSON
                        </button>
                      </div>
                    </div>
                  </div>
                </section>
                {project.lore_entries.length === 0 ? <section className="panel"><p className="muted-text">No lore entries yet.</p></section> : null}
                {project.lore_entries.map((entry) => (
                  <LoreEditor
                    key={entry.id}
                    lore={entry}
                    editable={isProjectEditable}
                    loading={loading}
                    onSave={handleSaveLore}
                    onDelete={handleDeleteLore}
                    onGeneratePrompt={handleGenerateLorePrompt}
                    onGenerateImage={handleGenerateLoreImage}
                    onPromptDraftChange={handleLorePromptDraftChange}
                    onApproveCandidate={handleApproveLoreCandidate}
                    promptDraft={readPromptDraft("lore", entry.id, "lore")}
                    candidates={readCandidates("lore", entry.id, "lore")}
                    slotStatus={readImageSlotStatus("lore", entry.id, "lore")}
                  />
                ))}
              </>
            ) : null}

            {workspaceTab === "user" ? (
              <section className="panel">
                <div className="panel-header">
                  <h2>User Persona</h2>
                  <div className="action-row">
                    <button className="ghost-button" disabled={!isProjectEditable || loading} onClick={() => void handleGenerateUser()}>
                      Regenerate User
                    </button>
                  </div>
                </div>
                <div className="project-grid">
                  <label className="field">
                    <span>Name</span>
                    <input
                      disabled={!isProjectEditable}
                      value={project.user_profile.name}
                      onChange={(e) =>
                        setProject({
                          ...project,
                          user_profile: { ...project.user_profile, name: e.target.value },
                        })
                      }
                      onBlur={() => void handleSaveUserProfile({ name: project.user_profile.name })}
                    />
                  </label>
                  <label className="field">
                    <span>Title</span>
                    <input
                      disabled={!isProjectEditable}
                      value={project.user_profile.title}
                      onChange={(e) =>
                        setProject({
                          ...project,
                          user_profile: { ...project.user_profile, title: e.target.value },
                        })
                      }
                      onBlur={() => void handleSaveUserProfile({ title: project.user_profile.title })}
                    />
                  </label>
                  <label className="field">
                    <span>Tags</span>
                    <input
                      disabled={!isProjectEditable}
                      value={joinTags(project.user_profile.tags)}
                      onChange={(e) =>
                        setProject({
                          ...project,
                          user_profile: { ...project.user_profile, tags: parseTags(e.target.value) },
                        })
                      }
                      onBlur={() => void handleSaveUserProfile({ tags: project.user_profile.tags })}
                    />
                  </label>
                  <label className="field scenario-field">
                    <span>Description</span>
                    <textarea
                      rows={3}
                      disabled={!isProjectEditable}
                      value={project.user_profile.description}
                      onChange={(e) =>
                        setProject({
                          ...project,
                          user_profile: { ...project.user_profile, description: e.target.value },
                        })
                      }
                      onBlur={() => void handleSaveUserProfile({ description: project.user_profile.description })}
                    />
                  </label>
                  <label className="field scenario-field">
                    <span>Appearance Summary</span>
                    <textarea
                      rows={3}
                      disabled={!isProjectEditable}
                      value={project.user_profile.appearance_summary}
                      onChange={(e) =>
                        setProject({
                          ...project,
                          user_profile: { ...project.user_profile, appearance_summary: e.target.value },
                        })
                      }
                      onBlur={() => void handleSaveUserProfile({ appearance_summary: project.user_profile.appearance_summary })}
                    />
                  </label>
                  <label className="field">
                    <span>Booru Character Name</span>
                    <input
                      disabled={!isProjectEditable}
                      value={project.user_profile.booru_character_name}
                      onChange={(e) =>
                        setProject({
                          ...project,
                          user_profile: { ...project.user_profile, booru_character_name: e.target.value },
                        })
                      }
                      onBlur={() => void handleSaveUserProfile({ booru_character_name: project.user_profile.booru_character_name })}
                    />
                  </label>
                  <label className="field">
                    <span>Booru Copyright</span>
                    <input
                      disabled={!isProjectEditable}
                      value={project.user_profile.booru_copyright}
                      onChange={(e) =>
                        setProject({
                          ...project,
                          user_profile: { ...project.user_profile, booru_copyright: e.target.value },
                        })
                      }
                      onBlur={() => void handleSaveUserProfile({ booru_copyright: project.user_profile.booru_copyright })}
                    />
                  </label>
                  <label className="field scenario-field">
                    <span>Persona Note</span>
                    <textarea
                      rows={3}
                      disabled={!isProjectEditable}
                      value={project.user_profile.persona_note}
                      onChange={(e) =>
                        setProject({
                          ...project,
                          user_profile: { ...project.user_profile, persona_note: e.target.value },
                        })
                      }
                      onBlur={() => void handleSaveUserProfile({ persona_note: project.user_profile.persona_note })}
                    />
                  </label>
                  <label className="field">
                    <span>Persona Note Depth</span>
                    <input
                      type="number"
                      min={0}
                      disabled={!isProjectEditable}
                      value={project.user_profile.persona_note_depth}
                      onChange={(e) =>
                        setProject({
                          ...project,
                          user_profile: { ...project.user_profile, persona_note_depth: Number(e.target.value) || 0 },
                        })
                      }
                      onBlur={() => void handleSaveUserProfile({ persona_note_depth: project.user_profile.persona_note_depth })}
                    />
                  </label>
                  <label className="field">
                    <span>Persona Note Role</span>
                    <select
                      disabled={!isProjectEditable}
                      value={project.user_profile.persona_note_role}
                      onChange={(e) =>
                        setProject({
                          ...project,
                          user_profile: { ...project.user_profile, persona_note_role: e.target.value as MessageRole },
                        })
                      }
                      onBlur={() => void handleSaveUserProfile({ persona_note_role: project.user_profile.persona_note_role })}
                    >
                      {messageRoles.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>Personality</span>
                    <textarea
                      rows={3}
                      disabled={!isProjectEditable}
                      value={project.user_profile.personality}
                      onChange={(e) =>
                        setProject({
                          ...project,
                          user_profile: { ...project.user_profile, personality: e.target.value },
                        })
                      }
                      onBlur={() => void handleSaveUserProfile({ personality: project.user_profile.personality })}
                    />
                  </label>
                  <label className="field">
                    <span>Scenario Role</span>
                    <textarea
                      rows={3}
                      disabled={!isProjectEditable}
                      value={project.user_profile.scenario_role}
                      onChange={(e) =>
                        setProject({
                          ...project,
                          user_profile: { ...project.user_profile, scenario_role: e.target.value },
                        })
                      }
                      onBlur={() => void handleSaveUserProfile({ scenario_role: project.user_profile.scenario_role })}
                    />
                  </label>
                  <label className="field scenario-field">
                    <span>First Message</span>
                    <textarea
                      rows={4}
                      disabled={!isProjectEditable}
                      value={project.user_profile.first_message}
                      onChange={(e) =>
                        setProject({
                          ...project,
                          user_profile: { ...project.user_profile, first_message: e.target.value },
                        })
                      }
                      onBlur={() => void handleSaveUserProfile({ first_message: project.user_profile.first_message })}
                    />
                  </label>
                </div>
                <div className="settings-card" style={{ marginTop: "1rem" }}>
                  <div className="panel-header">
                    <h3>Persona Exports</h3>
                    <button className="ghost-button" disabled={loading} onClick={() => void handleSyncToSillyTavern()}>
                      Sync to SillyTavern
                    </button>
                  </div>
                  <p className="muted-text">
                    Export the SillyTavern persona bundle, a portable persona card, or the full project bundle with GM card, companion
                    cards, lorebook, and persona assets.
                  </p>
                  <div className="project-list">
                    <div className="export-card">
                      <strong>{project.user_profile.name || "Persona"} Bundle</strong>
                      <div className="action-row">
                        <button className="ghost-button" onClick={() => void downloadExport(userExportUrl(project.id), `${project.name}-persona.json`)}>
                          JSON
                        </button>
                      </div>
                    </div>
                    <div className="export-card">
                      <strong>{project.user_profile.name || "Persona"} Card</strong>
                      <div className="action-row">
                        <button className="ghost-button" onClick={() => void downloadExport(personaCardExportJsonUrl(project.id), `${project.user_profile.name || "User"}-persona-card.json`)}>
                          JSON
                        </button>
                        <button className="ghost-button" onClick={() => void downloadExport(personaCardExportImageUrl(project.id, "png"), `${project.user_profile.name || "User"}-persona-card.png`)}>
                          PNG
                        </button>
                        <button className="ghost-button" onClick={() => void downloadExport(personaCardExportImageUrl(project.id, "webp"), `${project.user_profile.name || "User"}-persona-card.webp`)}>
                          WEBP
                        </button>
                      </div>
                    </div>
                    <div className="export-card">
                      <strong>{project.name} Bundle</strong>
                      <div className="action-row">
                        <button className="ghost-button" onClick={() => void downloadExport(bundleExportUrl(project.id), `${project.name}-bundle.json`)}>
                          JSON
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
                {project.user_profile.portrait_url || project.user_profile.cowboy_shot_url || project.user_profile.fullbody_shot_url ? (
                  <div className="media-preview-grid" style={{ marginTop: "1rem" }}>
                    {project.user_profile.portrait_url ? <img src={project.user_profile.portrait_url} alt={`${project.user_profile.name} portrait`} /> : null}
                    {project.user_profile.cowboy_shot_url ? <img src={project.user_profile.cowboy_shot_url} alt={`${project.user_profile.name} cowboy shot`} /> : null}
                    {project.user_profile.fullbody_shot_url ? <img src={project.user_profile.fullbody_shot_url} alt={`${project.user_profile.name} full body`} /> : null}
                  </div>
                ) : null}
                <div className="project-grid" style={{ marginTop: "1rem" }}>
                  {allShotFormats.map((format) => {
                    const draft = readPromptDraft("user", project.id, format);
                    const candidates = readCandidates("user", project.id, format);
                    const slotStatus = readImageSlotStatus("user", project.id, format);
                    const label =
                      format === "portrait"
                        ? "Portrait"
                        : format === "cowboy_shot"
                          ? "Cowboy Shot"
                          : "Full Body";
                    return (
                      <div key={format} className="settings-card">
                        <div className="panel-header">
                          <h3>{label} Prompt + Image</h3>
                          {draft.style_profile ? <span className="badge muted">{draft.style_profile}</span> : null}
                        </div>
                        <div className="action-row" style={{ marginBottom: "0.8rem" }}>
                          <button className="ghost-button" disabled={!isProjectEditable || loading || Boolean(slotStatus)} onClick={() => void handleGenerateUserPrompt(format)}>
                            {slotStatus === "Generating prompt..." ? "Generating..." : "Generate Prompt"}
                          </button>
                          <button
                            className="primary-button"
                            disabled={!isProjectEditable || loading || Boolean(slotStatus) || !draft.prompt.trim()}
                            onClick={() => void handleGenerateUserImage(format)}
                          >
                            {slotStatus === "Generating image..." ? "Generating..." : "Generate Image"}
                          </button>
                        </div>
                        {slotStatus ? <p className="muted-text">{slotStatus}</p> : null}
                        <label className="field">
                          <span>Instruction (optional)</span>
                          <input
                            value={draft.instruction}
                            disabled={!isProjectEditable || loading || Boolean(slotStatus)}
                            onChange={(e) => handleUserPromptDraftChange(format, "instruction", e.target.value)}
                          />
                        </label>
                        <label className="field">
                          <span>Prompt</span>
                          <textarea
                            rows={4}
                            value={draft.prompt}
                            disabled={!isProjectEditable || loading || Boolean(slotStatus)}
                            onChange={(e) => handleUserPromptDraftChange(format, "prompt", e.target.value)}
                          />
                        </label>
                        <label className="field">
                          <span>Negative Prompt</span>
                          <textarea
                            rows={3}
                            value={draft.negative_prompt}
                            disabled={!isProjectEditable || loading || Boolean(slotStatus)}
                            onChange={(e) => handleUserPromptDraftChange(format, "negative_prompt", e.target.value)}
                          />
                        </label>
                        {candidates.length > 0 ? (
                          <div className="variant-grid">
                            {candidates.map((candidate) => (
                              <div key={candidate.id} className="variant-card">
                                <img src={candidate.image_url} alt={`${project.user_profile.name} ${label} candidate`} />
                                <div className="action-row">
                                  <span className={`badge ${candidate.approved ? "success" : "muted"}`}>
                                    {candidate.approved ? "Cover" : "Candidate"}
                                  </span>
                                  <button
                                    className="ghost-button"
                                    disabled={!isProjectEditable || loading || Boolean(slotStatus) || candidate.approved}
                                    onClick={() => void handleApproveUserCandidate(format, candidate.id)}
                                  >
                                    Approve Cover
                                  </button>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="muted-text">No generated candidates yet.</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            ) : null}

            {workspaceTab === "compatibility" ? (
              <section className="panel">
                <div className="panel-header">
                  <div>
                    <h2>Compatibility Inspector</h2>
                    <p className="muted-text">
                      Checks card v2 fields, macros, lorebook insertion settings, persona exports, token budget, and sync-ready paths before
                      SillyTavern export.
                    </p>
                  </div>
                  <div className="action-row">
                    <button className="primary-button" disabled={loading} onClick={() => void handleInspectCompatibility()}>
                      Run Check
                    </button>
                    <button className="ghost-button" disabled={loading} onClick={() => void handleSyncToSillyTavern()}>
                      Sync to SillyTavern
                    </button>
                  </div>
                </div>

                <div className="stat-grid">
                  <div className="stat-card">
                    <span>Status</span>
                    <strong>{compatibilityReport?.status ?? "Not checked"}</strong>
                  </div>
                  <div className="stat-card">
                    <span>Critical</span>
                    <strong>{compatibilityReport?.critical_count ?? 0}</strong>
                  </div>
                  <div className="stat-card">
                    <span>Warnings</span>
                    <strong>{compatibilityReport?.warning_count ?? 0}</strong>
                  </div>
                </div>

                {compatibilityReport ? (
                  <div className="settings-card">
                    <div className="panel-header compact">
                      <span
                        className={`badge ${
                          compatibilityReport.status === "blocked"
                            ? "danger"
                            : compatibilityReport.status === "warnings"
                              ? "warning"
                              : "success"
                        }`}
                      >
                        {compatibilityReport.status}
                      </span>
                      <span className="muted-text">Checked {new Date(compatibilityReport.checked_at).toLocaleString()}</span>
                    </div>
                    {compatibilityReport.issues.length > 0 ? (
                      <div className="preview-results">
                        {compatibilityReport.issues.map((issue) => (
                          <div key={`${issue.target}-${issue.code}-${issue.message}`} className="settings-card">
                            <div className="action-row">
                              <span className={`badge ${issue.severity === "critical" ? "danger" : "warning"}`}>{issue.severity}</span>
                              <span className="badge muted">{issue.code}</span>
                            </div>
                            <p>{issue.message}</p>
                            <p className="muted-text">{issue.target}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="muted-text">No compatibility issues detected.</p>
                    )}
                  </div>
                ) : (
                  <div className="settings-card">
                    <p className="muted-text">Run the inspector to validate this project before PNG/WebP export or SillyTavern sync.</p>
                  </div>
                )}
              </section>
            ) : null}

            {workspaceTab === "settings" ? (
              <>
                <section className="panel">
                  <div className="panel-header">
                    <h2>Model Runtime</h2>
                    <div className="action-row">
                      <button className="ghost-button" disabled={!modelSettingsDraft || loading} onClick={() => void handleTestModelSettings()}>
                        Test Connection
                      </button>
                      <button className="primary-button" disabled={!modelSettingsDraft || loading} onClick={() => void handleSaveModelSettings()}>
                        Save
                      </button>
                    </div>
                  </div>
                  {modelSettingsDraft ? (
                    <div className="project-grid">
                      <label className="field">
                        <span>Provider</span>
                        <select
                          value={modelSettingsDraft.runtime.provider}
                          onChange={(e) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              runtime: { ...modelSettingsDraft.runtime, provider: e.target.value as typeof modelSettingsDraft.runtime.provider },
                            })
                          }
                        >
                          <option value="koboldcpp">koboldcpp</option>
                          <option value="ollama">ollama</option>
                          <option value="openai_compatible">openai_compatible</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>Base URL</span>
                        <input
                          value={modelSettingsDraft.runtime.base_url}
                          onChange={(e) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              runtime: { ...modelSettingsDraft.runtime, base_url: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Default Model</span>
                        <input
                          value={modelSettingsDraft.runtime.default_model}
                          onChange={(e) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              runtime: { ...modelSettingsDraft.runtime, default_model: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Timeout (s)</span>
                        <input
                          type="number"
                          value={modelSettingsDraft.runtime.timeout_s}
                          onChange={(e) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              runtime: { ...modelSettingsDraft.runtime, timeout_s: Number(e.target.value) },
                            })
                          }
                        />
                      </label>
                      <label className="field scenario-field">
                        <span>API Key</span>
                        <input
                          value={modelSettingsDraft.runtime.api_key}
                          onChange={(e) =>
                            setModelSettingsDraft({
                              ...modelSettingsDraft,
                              runtime: { ...modelSettingsDraft.runtime, api_key: e.target.value },
                            })
                          }
                        />
                      </label>
                    </div>
                  ) : (
                    <p className="muted-text">Loading model settings…</p>
                  )}
                  {connectionTest ? (
                    <div className="settings-card">
                      <p className="muted-text">{connectionTest.status}: {connectionTest.message}</p>
                    </div>
                  ) : null}
                </section>

                <section className="panel">
                  <div className="panel-header">
                    <h2>Task Prompt Templates</h2>
                    <span className="badge muted">Global</span>
                  </div>
                  {modelSettingsDraft && selectedTaskProfile ? (
                    <div className="project-grid">
                      <label className="field">
                        <span>Task</span>
                        <select value={templateTask} onChange={(e) => setTemplateTask(e.target.value as GenerationTask)}>
                          {modelSettingsDraft.task_catalog.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field">
                        <span>Model Override</span>
                        <input
                          value={selectedTaskProfile.model_override ?? ""}
                          onChange={(e) => updateTemplateTaskProfile(templateTask, { model_override: e.target.value || null })}
                        />
                      </label>
                      <label className="field">
                        <span>Temperature Override</span>
                        <input
                          type="number"
                          step="0.05"
                          value={selectedTaskProfile.temperature_override ?? ""}
                          onChange={(e) =>
                            updateTemplateTaskProfile(templateTask, {
                              temperature_override: e.target.value === "" ? null : Number(e.target.value),
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Top P Override</span>
                        <input
                          type="number"
                          step="0.05"
                          value={selectedTaskProfile.top_p_override ?? ""}
                          onChange={(e) =>
                            updateTemplateTaskProfile(templateTask, {
                              top_p_override: e.target.value === "" ? null : Number(e.target.value),
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Max Output Tokens Override</span>
                        <input
                          type="number"
                          value={selectedTaskProfile.max_output_tokens_override ?? ""}
                          onChange={(e) =>
                            updateTemplateTaskProfile(templateTask, {
                              max_output_tokens_override: e.target.value === "" ? null : Number(e.target.value),
                            })
                          }
                        />
                      </label>
                      <label className="field scenario-field">
                        <span>System Template</span>
                        <textarea
                          rows={8}
                          value={selectedTaskProfile.system_template}
                          onChange={(e) => updateTemplateTaskProfile(templateTask, { system_template: e.target.value })}
                        />
                      </label>
                      <label className="field scenario-field">
                        <span>User Template</span>
                        <textarea
                          rows={14}
                          value={selectedTaskProfile.user_template}
                          onChange={(e) => updateTemplateTaskProfile(templateTask, { user_template: e.target.value })}
                        />
                      </label>
                      <div className="scenario-field settings-card">
                        <p className="muted-text">
                          Variables available:
                          {" "}
                          {(modelSettingsDraft.task_catalog.find((item) => item.id === templateTask)?.variables ?? []).join(", ")}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <p className="muted-text">Loading task template editor…</p>
                  )}
                </section>

                <section className="panel">
                  <div className="panel-header">
                    <h2>Prompt Preview</h2>
                    <div className="action-row">
                      <button className="ghost-button" disabled={!project || loading} onClick={() => void handlePreviewPrompt()}>
                        Render
                      </button>
                      <button className="ghost-button" disabled={loading || (!previewInstruction && !previewResult)} onClick={handleClearPromptPreviewContext}>
                        Clear LLM Context
                      </button>
                    </div>
                  </div>
                  <div className="project-grid">
                    <label className="field">
                      <span>Task</span>
                      <select value={previewTask} onChange={(e) => setPreviewTask(e.target.value as typeof previewTask)}>
                        {(modelSettingsDraft?.task_catalog ?? []).map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.id}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field scenario-field">
                      <span>Instruction</span>
                      <input value={previewInstruction} onChange={(e) => setPreviewInstruction(e.target.value)} />
                    </label>
                    {previewResult ? (
                      <>
                        <label className="field scenario-field">
                          <span>System Prompt</span>
                          <textarea readOnly rows={6} value={previewResult.system_prompt} />
                        </label>
                        <label className="field scenario-field">
                          <span>User Prompt</span>
                          <textarea readOnly rows={8} value={previewResult.user_prompt} />
                        </label>
                      </>
                    ) : null}
                  </div>
                </section>

                <section className="panel">
                  <div className="panel-header">
                    <h2>Image Generation</h2>
                    <div className="action-row">
                      <button className="ghost-button" disabled={loading} onClick={() => void handleRefreshImageModels()}>
                        Rescan Models
                      </button>
                      <button className="ghost-button" disabled={!mediaSettingsDraft || loading} onClick={() => void handleTestMediaSettings()}>
                        Test
                      </button>
                      <button className="primary-button" disabled={!mediaSettingsDraft || loading} onClick={() => void handleSaveMediaSettings()}>
                        Save
                      </button>
                    </div>
                  </div>
                  {mediaSettingsDraft ? (
                    <div className="project-grid">
                      <label className="field">
                        <span>Provider</span>
                        <select
                          value={mediaSettingsDraft.image.provider}
                          onChange={(e) =>
                            setMediaSettingsDraft({
                              ...mediaSettingsDraft,
                              image: { ...mediaSettingsDraft.image, provider: e.target.value as typeof mediaSettingsDraft.image.provider },
                            })
                          }
                        >
                          <option value="mock">mock</option>
                          <option value="diffusers">diffusers</option>
                          <option value="comfyui">comfyui</option>
                        </select>
                      </label>
                      {mediaSettingsDraft.image.provider === "comfyui" ? (
                        <>
                          <label className="field">
                            <span>ComfyUI Endpoint</span>
                            <input
                              value={mediaSettingsDraft.image.comfy_endpoint}
                              onChange={(e) =>
                                setMediaSettingsDraft({
                                  ...mediaSettingsDraft,
                                  image: { ...mediaSettingsDraft.image, comfy_endpoint: e.target.value },
                                })
                              }
                            />
                          </label>
                          <label className="field">
                            <span>ComfyUI Timeout (s)</span>
                            <input
                              type="number"
                              value={mediaSettingsDraft.image.comfy_timeout_s}
                              onChange={(e) =>
                                setMediaSettingsDraft({
                                  ...mediaSettingsDraft,
                                  image: { ...mediaSettingsDraft.image, comfy_timeout_s: Number(e.target.value) || 300 },
                                })
                              }
                            />
                          </label>
                          <label className="field scenario-field">
                            <span>ComfyUI Workflow JSON</span>
                            <textarea
                              rows={5}
                              value={mediaSettingsDraft.image.comfy_workflow_json}
                              onChange={(e) =>
                                setMediaSettingsDraft({
                                  ...mediaSettingsDraft,
                                  image: { ...mediaSettingsDraft.image, comfy_workflow_json: e.target.value },
                                })
                              }
                              placeholder="Leave empty for the built-in txt2img workflow."
                            />
                          </label>
                        </>
                      ) : null}
                      <label className="field">
                        <span>Checkpoint Root</span>
                        <input
                          value={mediaSettingsDraft.image.checkpoint_root}
                          onChange={(e) =>
                            setMediaSettingsDraft({
                              ...mediaSettingsDraft,
                              image: { ...mediaSettingsDraft.image, checkpoint_root: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Default Model</span>
                        <select
                          value={mediaSettingsDraft.image.default_model}
                          onChange={(e) =>
                            setMediaSettingsDraft({
                              ...mediaSettingsDraft,
                              image: { ...mediaSettingsDraft.image, default_model: e.target.value },
                            })
                          }
                        >
                          <option value="">auto-select first discovered</option>
                          {(imageModels?.models ?? []).map((model) => (
                            <option key={model.value} value={model.value}>
                              {model.label} ({model.kind})
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="field">
                        <span>Device</span>
                        <select
                          value={mediaSettingsDraft.image.device}
                          onChange={(e) =>
                            setMediaSettingsDraft({
                              ...mediaSettingsDraft,
                              image: { ...mediaSettingsDraft.image, device: e.target.value },
                            })
                          }
                        >
                          <option value="auto">auto</option>
                          <option value="cuda">cuda</option>
                          <option value="cpu">cpu</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>Dtype</span>
                        <select
                          value={mediaSettingsDraft.image.dtype}
                          onChange={(e) =>
                            setMediaSettingsDraft({
                              ...mediaSettingsDraft,
                              image: { ...mediaSettingsDraft.image, dtype: e.target.value },
                            })
                          }
                        >
                          <option value="auto">auto</option>
                          <option value="fp16">fp16</option>
                          <option value="bf16">bf16</option>
                          <option value="fp32">fp32</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>Sampler</span>
                        <select
                          value={mediaSettingsDraft.image.sampler}
                          onChange={(e) =>
                            setMediaSettingsDraft({
                              ...mediaSettingsDraft,
                              image: { ...mediaSettingsDraft.image, sampler: e.target.value },
                            })
                          }
                        >
                          <option value="res_multistep">res_multistep</option>
                          <option value="dpmpp_sde">dpmpp_sde</option>
                          <option value="dpmpp_2s_ancestral">dpmpp_2s_ancestral</option>
                          <option value="lcm">lcm</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>Scheduler</span>
                        <select
                          value={mediaSettingsDraft.image.scheduler}
                          onChange={(e) =>
                            setMediaSettingsDraft({
                              ...mediaSettingsDraft,
                              image: { ...mediaSettingsDraft.image, scheduler: e.target.value },
                            })
                          }
                        >
                          <option value="simple">simple</option>
                          <option value="karras">karras</option>
                          <option value="beta">beta</option>
                          <option value="gits">gits</option>
                          <option value="kl_optimal">kl_optimal</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>Steps</span>
                        <input
                          type="number"
                          value={mediaSettingsDraft.image.steps}
                          onChange={(e) =>
                            setMediaSettingsDraft({
                              ...mediaSettingsDraft,
                              image: { ...mediaSettingsDraft.image, steps: Number(e.target.value) },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>CFG Scale</span>
                        <input
                          type="number"
                          step="0.1"
                          value={mediaSettingsDraft.image.cfg_scale}
                          onChange={(e) =>
                            setMediaSettingsDraft({
                              ...mediaSettingsDraft,
                              image: { ...mediaSettingsDraft.image, cfg_scale: Number(e.target.value) },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Width</span>
                        <input
                          type="number"
                          value={mediaSettingsDraft.image.width}
                          onChange={(e) =>
                            setMediaSettingsDraft({
                              ...mediaSettingsDraft,
                              image: { ...mediaSettingsDraft.image, width: Number(e.target.value) },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Height</span>
                        <input
                          type="number"
                          value={mediaSettingsDraft.image.height}
                          onChange={(e) =>
                            setMediaSettingsDraft({
                              ...mediaSettingsDraft,
                              image: { ...mediaSettingsDraft.image, height: Number(e.target.value) },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Variant Count</span>
                        <input
                          type="number"
                          value={mediaSettingsDraft.image.variant_count}
                          onChange={(e) =>
                            setMediaSettingsDraft({
                              ...mediaSettingsDraft,
                              image: { ...mediaSettingsDraft.image, variant_count: Number(e.target.value) },
                            })
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Seed Mode</span>
                        <select
                          value={mediaSettingsDraft.image.seed_mode}
                          onChange={(e) =>
                            setMediaSettingsDraft({
                              ...mediaSettingsDraft,
                              image: {
                                ...mediaSettingsDraft.image,
                                seed_mode: e.target.value as typeof mediaSettingsDraft.image.seed_mode,
                              },
                            })
                          }
                        >
                          <option value="random">random</option>
                          <option value="fixed">fixed</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>Seed</span>
                        <input
                          type="number"
                          value={mediaSettingsDraft.image.seed ?? ""}
                          onChange={(e) =>
                            setMediaSettingsDraft({
                              ...mediaSettingsDraft,
                              image: {
                                ...mediaSettingsDraft.image,
                                seed: e.target.value === "" ? null : Number(e.target.value),
                              },
                            })
                          }
                        />
                      </label>
                      <label className="field scenario-field">
                        <span>Default Negative Prompt</span>
                        <textarea
                          rows={3}
                          value={mediaSettingsDraft.image.default_negative_prompt}
                          onChange={(e) =>
                            setMediaSettingsDraft({
                              ...mediaSettingsDraft,
                              image: { ...mediaSettingsDraft.image, default_negative_prompt: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label className="upload-button">
                        Upload Model
                        <input type="file" onChange={(e) => void handleUploadImageModel(e.target.files?.[0] ?? null)} />
                      </label>
                    </div>
                  ) : (
                    <p className="muted-text">Loading media settings…</p>
                  )}
                  {mediaTest ? (
                    <div className="settings-card">
                      <p className="muted-text">{mediaTest.image.status}: {mediaTest.image.message}</p>
                    </div>
                  ) : null}
                  {imageModels ? (
                    <div className="settings-card">
                      <p className="muted-text">Checkpoint root: <code>{imageModels.root_path}</code></p>
                      <p className="muted-text">Discovered models: {imageModels.models.length}</p>
                      {imageModels.models.length > 0 ? (
                        <div className="token-cloud">
                          {imageModels.models.map((model) => (
                            <span key={model.value} className={`code-chip ${mediaSettingsDraft?.image.default_model === model.value ? "active-chip" : ""}`}>
                              {model.label}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  <div className="settings-card">
                    <p className="muted-text">
                      For local GPU rendering, set provider to <code>diffusers</code> and device to <code>auto</code> or <code>cuda</code>.
                    </p>
                    <p className="muted-text">
                      Prompt guidance is automatic: models with names containing <code>noob</code> use NoobAI-style
                      Danbooru tag formatting, and models with <code>illust</code>/<code>illustrious</code> use Illustrious-style
                      anime prompt structuring.
                    </p>
                  </div>
                </section>
              </>
            ) : null}

            <section className="panel">
              <div className="panel-header">
                <h2>Recent Runs</h2>
                <span className="badge muted">{latestRuns.length}</span>
              </div>
              {latestRuns.length === 0 ? (
                <p className="muted-text">No generation runs yet.</p>
              ) : (
                <div className="project-list">
                  {latestRuns.map((run) => (
                    <div key={run.id} className="job-card">
                      <strong>{run.task_type}</strong>
                      <p className="muted-text">{run.status}{run.error_text ? ` • ${run.error_text}` : ""}</p>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        ) : (
          <section className="empty-state panel">
            <h2>No project selected</h2>
            <p className="muted-text">Create or select a project to start generating SillyTavern cards.</p>
          </section>
        )}
      </main>
    </div>
  );
}

export default App;
