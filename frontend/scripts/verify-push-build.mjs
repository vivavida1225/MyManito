import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const assetsDirectory = join(process.cwd(), "dist", "assets");
const bundle = readdirSync(assetsDirectory)
  .filter((name) => name.endsWith(".js"))
  .map((name) => readFileSync(join(assetsDirectory, name), "utf8"))
  .join("\n");
const envFile = readFileSync(join(process.cwd(), ".env"), "utf8");
const envPublicKey = envFile.match(/^VITE_IOS_WEB_PUSH_VAPID_PUBLIC_KEY=(.*)$/m)?.[1].trim() || "";
const publicKey = process.env.VITE_IOS_WEB_PUSH_VAPID_PUBLIC_KEY || envPublicKey;

const requiredValues = [
  publicKey,
  "/ios-web-push-sw.js",
  "/accounts/ios-web-push-subscriptions/",
  "/firebase-messaging-sw.js",
  "/accounts/web-push-devices/",
];
if (!publicKey || requiredValues.some((value) => !bundle.includes(value))) {
  throw new Error("The production bundle is missing a configured iOS or Android web push path.");
}
if (bundle.includes("http://localhost:5173/auth/kakao/callback")) {
  throw new Error("The production bundle contains the local Kakao redirect URI.");
}

console.log("Verified iOS and Android web push paths in the production bundle.");
