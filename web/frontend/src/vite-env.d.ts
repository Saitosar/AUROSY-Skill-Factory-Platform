/// <reference types="vite/client" />



declare const __APP_VERSION__: string;



declare module "@mujoco/mujoco/mujoco.wasm?url" {

  const src: string;

  export default src;

}



interface ImportMetaEnv {

  readonly VITE_API_BASE: string | undefined;

  readonly VITE_PLATFORM_USER_ID: string | undefined;

}



interface ImportMeta {

  readonly env: ImportMetaEnv;

}

