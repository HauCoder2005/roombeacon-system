import type { MetadataRoute } from "next";
import { getServerDistricts } from "@/lib/api/server";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const baseUrl = "https://roombeacon.vn";

  const staticRoutes: MetadataRoute.Sitemap = [
    {
      url: `${baseUrl}/`,
      lastModified: new Date(),
      changeFrequency: "daily",
      priority: 1,
    },
    {
      url: `${baseUrl}/tim-phong`,
      lastModified: new Date(),
      changeFrequency: "daily",
      priority: 0.9,
    },
    {
      url: `${baseUrl}/khu-vuc`,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 0.8,
    },
    {
      url: `${baseUrl}/dinh-gia`,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 0.85,
    },
  ];

  try {
    const districtsRes = await getServerDistricts({ per_page: 100 });
    const districts = districtsRes.data || [];

    const districtRoutes: MetadataRoute.Sitemap = districts.map((d) => ({
      url: `${baseUrl}/khu-vuc/${d.id}`,
      lastModified: new Date(),
      changeFrequency: "daily",
      priority: 0.85,
    }));

    return [...staticRoutes, ...districtRoutes];
  } catch {
    return staticRoutes;
  }
}
