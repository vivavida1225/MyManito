import { createPinia } from "pinia";

// Router guard와 Vue 앱이 동일한 Pinia 인스턴스를 사용한다.
export const pinia = createPinia();
