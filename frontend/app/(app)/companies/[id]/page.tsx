import { CompanyDetail } from "@/components/companies/company-detail";

export default async function CompanyDetailPage(props: PageProps<"/companies/[id]">) {
  const { id } = await props.params;
  return <CompanyDetail companyId={id} />;
}
