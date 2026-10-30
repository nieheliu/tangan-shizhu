import http from "./http";

export interface ProfilePreferences {
  tastes: string[];
  cuisines: string[];
}

export interface ProfileView {
  gender: string | null;
  birth_year: number | null;
  height_cm: number | null;
  weight_kg: number | null;
  activity_level: string | null;
  diseases: string[];
  fasting_glucose: number | null;
  hba1c: number | null;
  allergies: string[];
  dislikes: string[];
  preferences: ProfilePreferences;
  daily_kcal_target: number | null;
  age: number | null;
  bmi: number | null;
  ideal_weight_kg: number | null;
  suggested_kcal: number | null;
  kcal_per_kg: number | null;
  kcal_source: string;
  recipe_allowed: boolean;
  recipe_block_message: string | null;
}

export interface ProfilePreview {
  age: number | null;
  bmi: number | null;
  ideal_weight_kg: number | null;
  suggested_kcal: number | null;
  kcal_per_kg: number | null;
  kcal_source: string;
  can_save: boolean;
  block_message: string | null;
}

export interface ProfilePayload {
  gender: string;
  birth_year: number;
  height_cm: number;
  weight_kg: number;
  activity_level: string;
  diseases: string[];
  fasting_glucose: number | null;
  hba1c: number | null;
  allergies: string[];
  dislikes: string[];
  preferences: ProfilePreferences;
  daily_kcal_target: number | null;
}

export function fetchProfile() {
  return http.get<ProfileView>("/api/v1/profile");
}

export function saveProfile(payload: ProfilePayload) {
  return http.put<ProfileView>("/api/v1/profile", payload);
}

export function previewProfile(payload: {
  birth_year?: number;
  height_cm?: number;
  weight_kg?: number;
  activity_level?: string;
}) {
  return http.post<ProfilePreview>("/api/v1/profile/preview", payload);
}
