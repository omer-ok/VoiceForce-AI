"use client";

import dynamic from "next/dynamic";

const VoiceForceCall = dynamic(() => import("./voiceforce-call"), {
  ssr: false,
});

export default function VoiceForceCallLoader() {
  return <VoiceForceCall />;
}
