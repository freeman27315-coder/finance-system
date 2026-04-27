import { AppShell } from "@/components/app-shell";
import { ModuleOverview } from "@/components/module-overview";
import { sectionById, sectionIds } from "@/lib/navigation";

type SectionPageProps = {
  params: {
    section: string;
  };
};

export default function SectionPage({ params }: SectionPageProps) {
  const section = sectionById[params.section] ?? sectionById.assets;

  return (
    <AppShell activeSection={section.id}>
      <ModuleOverview section={section} />
    </AppShell>
  );
}

export function generateStaticParams() {
  return sectionIds
    .filter((section) => section !== "dashboard")
    .map((section) => ({ section }));
}
