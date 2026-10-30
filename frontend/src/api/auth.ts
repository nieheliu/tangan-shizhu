import http from "./http";

export interface UserPublic {
  id: number;
  username: string;
  role: string;
}

export async function login(username: string, password: string) {
  const response = await http.post<{ access_token: string }>("/api/v1/auth/login", {
    username,
    password,
  });
  return response.data.access_token;
}

export async function register(username: string, password: string) {
  await http.post<UserPublic>("/api/v1/auth/register", { username, password });
}

export async function fetchMe() {
  const response = await http.get<UserPublic>("/api/v1/auth/me");
  return response.data;
}
