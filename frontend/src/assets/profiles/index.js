import clodi0 from "./clodi-0.webp";
import clodi1 from "./clodi-1.webp";
import clodi2 from "./clodi-2.webp";
import clodi3 from "./clodi-3.webp";
import clodi4 from "./clodi-4.webp";
import clodi5 from "./clodi-5.webp";
import clodi6 from "./clodi-6.webp";
import clodi7 from "./clodi-7.webp";
import clodi8 from "./clodi-8.webp";
import mani0 from "./mani-0.webp";
import mani1 from "./mani-1.webp";
import mani2 from "./mani-2.webp";
import mani3 from "./mani-3.webp";
import mani4 from "./mani-4.webp";
import mani5 from "./mani-5.webp";
import mani6 from "./mani-6.webp";
import mani7 from "./mani-7.webp";
import mani8 from "./mani-8.webp";

export const DEFAULT_PROFILE_OPTIONS = [
  { key: "mani-0", label: "마니 프로필 1", image: mani0 },
  { key: "mani-1", label: "마니 프로필 2", image: mani1 },
  { key: "mani-2", label: "마니 프로필 3", image: mani2 },
  { key: "mani-3", label: "마니 프로필 4", image: mani3 },
  { key: "mani-4", label: "마니 프로필 5", image: mani4 },
  { key: "mani-5", label: "마니 프로필 6", image: mani5 },
  { key: "mani-6", label: "마니 프로필 7", image: mani6 },
  { key: "mani-7", label: "마니 프로필 8", image: mani7 },
  { key: "mani-8", label: "마니 프로필 9", image: mani8 },
  { key: "clodi-0", label: "클로디 프로필 1", image: clodi0 },
  { key: "clodi-1", label: "클로디 프로필 2", image: clodi1 },
  { key: "clodi-2", label: "클로디 프로필 3", image: clodi2 },
  { key: "clodi-3", label: "클로디 프로필 4", image: clodi3 },
  { key: "clodi-4", label: "클로디 프로필 5", image: clodi4 },
  { key: "clodi-5", label: "클로디 프로필 6", image: clodi5 },
  { key: "clodi-6", label: "클로디 프로필 7", image: clodi6 },
  { key: "clodi-7", label: "클로디 프로필 8", image: clodi7 },
  { key: "clodi-8", label: "클로디 프로필 9", image: clodi8 },
];

export function getDefaultProfileImage(avatarKey) {
  return DEFAULT_PROFILE_OPTIONS.find((profile) => profile.key === avatarKey)?.image || mani0;
}
