/// <reference types="vite/client" />

declare module "markdown-it";
declare module "dompurify";

declare module "vue-router" {
  interface RouteMeta {
    title?: string;
    public?: boolean;
  }
}
