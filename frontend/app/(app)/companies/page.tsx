"use client";

import { useQuery } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import Link from "next/link";
import { listCompanies } from "@/lib/api-client";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function CompaniesPage() {
  const companiesQuery = useQuery({ queryKey: ["companies"], queryFn: listCompanies });
  const companies = companiesQuery.data ?? [];

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Companies</h1>
        <p className="text-sm text-muted">
          Companies discovered across your indexed documents.
        </p>
      </div>

      {companiesQuery.isLoading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      )}

      {!companiesQuery.isLoading && companies.length === 0 && (
        <Card>
          <CardContent className="p-10 text-center text-sm text-muted">
            No companies yet — upload a document with a company name to see it here.
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {companies.map((c) => (
          <Link key={c.id} href={`/companies/${c.id}`}>
            <Card className="h-full transition-colors hover:border-indigo-500/40">
              <CardContent className="flex items-start gap-3 p-5">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-400">
                  <Building2 className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <div className="truncate font-medium text-foreground">{c.name}</div>
                  <div className="mt-0.5 text-xs text-muted">
                    {c.ticker ?? "No ticker"} {c.industry ? `· ${c.industry}` : ""}
                  </div>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
