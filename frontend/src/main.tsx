import { AppRoot } from "./app-root";
import { getOrCreateRoot } from "./lib/get-or-create-root";
import { registerSW } from "./pwa/register-sw";

import "streamdown/styles.css";
import "@fontsource-variable/cascadia-code";
import "@fontsource-variable/fira-code";
import "@fontsource-variable/jetbrains-mono";
import "@fontsource-variable/noto-sans-sc";
import "@fontsource-variable/noto-serif-sc";
import "@fontsource-variable/roboto-mono";
import "@fontsource-variable/source-code-pro";
import "@fontsource/ma-shan-zheng";
import "@fontsource/wdxl-lubrifont-sc";
import "@fontsource/zcool-kuaile";
import "@fontsource/zcool-xiaowei";

import "./styles/index.css";

registerSW();
getOrCreateRoot(document.getElementById("root")!).render(<AppRoot />);
