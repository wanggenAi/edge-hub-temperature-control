import { createApp } from "vue";

import App from "./App.vue";
import router from "./router";
import { useAuth } from "./composables/useAuth";
import "./style.css";

async function bootstrap() {
  const app = createApp(App);
  app.use(router);
  const { restoreSession } = useAuth();
  await restoreSession();
  app.mount("#app");
}

void bootstrap();
