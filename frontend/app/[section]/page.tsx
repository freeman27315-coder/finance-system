import { AppShell } from "@/components/app-shell";
import { AssetsPage } from "@/components/assets-page";
import { ModuleOverview } from "@/components/module-overview";
import { OperatorsPage } from "@/components/operators-page";
import { TaiwanPage } from "@/components/taiwan-page";
import { TaobaoPage } from "@/components/taobao-page";
import { VendorsPage } from "@/components/vendors-page";
import { XboxPage } from "@/components/xbox-page";
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
      {section.id === "assets" ? (
        <AssetsPage />
      ) : section.id === "vendors" ? (
        <VendorsPage />
      ) : section.id === "xbox" ? (
        <XboxPage />
      ) : section.id === "taobao" ? (
        <TaobaoPage />
      ) : section.id === "taiwan" ? (
        <TaiwanPage />
      ) : section.id === "operators" ? (
        <OperatorsPage />
      ) : (
        <ModuleOverview section={section} />
      )}
    </AppShell>
  );
}

export function generateStaticParams() {
  return sectionIds
    .filter((section) => section !== "dashboard")
    .map((section) => ({ section }));
}
