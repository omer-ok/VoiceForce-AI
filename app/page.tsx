import VoiceForceCallLoader from "@/components/voiceforce-call-loader";

export default function Home() {
  return (
    <main className="flex min-h-full flex-1 items-center justify-center overflow-hidden bg-[#07111f] px-5 py-10 font-sans sm:px-8">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.15),transparent_35%),radial-gradient(circle_at_bottom_right,rgba(14,165,233,0.12),transparent_35%)]" />
      <div className="relative z-10 w-full max-w-6xl">
        <VoiceForceCallLoader />
      </div>
    </main>
  );
}
