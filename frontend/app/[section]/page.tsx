import { AppShell } from "@/components/app-shell";
import { AssetsPage } from "@/components/assets-page";
import { ModuleOverview } from "@/components/module-overview";
import { VendorsPage } from "@/components/vendors-page";
import { XboxPage } from "@/components/xbox-page";
import { TaobaoPage } from "@/components/taobao-page";
import { TaiwanPage } from "@/components/taiwan-page";
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
      {section.id === "assets" ? <AssetsPage /> : null}
      {section.id === "vendors" ? <VendorsPage /> : null}
      {section.id === "xbox" ? <XboxPage /> : null}
      {section.id === "taobao" ? <TaobaoPage /> : null}
      {section.id === "taiwan" ? <TaiwanPage /> : null}
      {section.id !== "assets" &&
      section.id !== "vendors" &&
      section.id !== "xbox" &&
      section.id !== "taobao" &&
      section.id !== "taiwan" ? (
        <ModuleOverview section={section} />
      ) : null}
    </AppShell>
  );
}

export function generateStaticParams() {
  return sectionIds
    .filter((section) => section !== "dashboard")
    .map((section) => ({ section }));
}
