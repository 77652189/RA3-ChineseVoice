//////////////////////////////////////////////////////////////////////////////
// [CNVoice] picture enhancement for PostFX_LookupTable.fx (RA3 / Uprising, PC)
//
// Runs in the last full-screen pass before the UI is drawn:
//   - ambient occlusion from the engine's linear depth texture (WW3D.DepthTexture, scene units),
//     "crease" style: symmetric sample pairs, so flat and sloped ground stay untouched and only
//     concave spots (panel seams, gaps, where units and buildings meet the ground) get darker
//   - mild sharpening of the frame
//   - mild contrast / saturation grade
// Define CNV_SPLIT to apply it to the right half of the screen only (A/B screenshots).
//////////////////////////////////////////////////////////////////////////////
#ifndef CNV_ENHANCE_FXH
#define CNV_ENHANCE_FXH

#ifndef CNV_AO_STRENGTH
	#define CNV_AO_STRENGTH 0.75	// 0 = off
#endif
#ifndef CNV_AO_CREASE
	#define CNV_AO_CREASE 3.0		// concavity (scene units) that counts as fully occluded for one sample pair
#endif
#ifndef CNV_AO_RANGE
	#define CNV_AO_RANGE 25.0		// depth gaps beyond this (silhouettes, cliffs) fade out, avoiding halos
#endif
#ifndef CNV_AO_RADIUS
	#define CNV_AO_RADIUS 0.010		// outer sample ring, fraction of the screen height
#endif
#ifndef CNV_SHARPEN
	#define CNV_SHARPEN 0.30
#endif
#ifndef CNV_SATURATION
	#define CNV_SATURATION 0.90
#endif
#ifndef CNV_CONTRAST
	#define CNV_CONTRAST 0.20
#endif

SAMPLER_2D_BEGIN( CnvDepthTexture,
	string SasBindAddress = "WW3D.DepthTexture";
	)
	MinFilter = Point;
	MagFilter = Point;
	MipFilter = Point;
	AddressU = Clamp;
	AddressV = Clamp;
SAMPLER_2D_END

float CnvDepth(float2 uv)
{
	return tex2Dlod(SAMPLER(CnvDepthTexture), float4(uv, 0, 0)).x;
}

#ifndef CNV_AO_CREASE_MIN
	#define CNV_AO_CREASE_MIN 0.8	// concavity below this is ignored: the folds between big terrain triangles
#endif

// 1 = open, lower = occluded. px = size of one pixel in texture coordinates.
float CnvAmbientOcclusion(float2 uv, float2 px)
{
	float d0 = CnvDepth(uv);
	float2 scale = float2(px.x / px.y, 1) * CNV_AO_RADIUS;	// keep the sample ring round on wide screens
	// per-pixel rotation of the sample pattern (interleaved gradient noise): fine grain instead of banding
	float2 p = floor(uv / px);
	float jitter = frac(52.9829189 * frac(dot(p, float2(0.06711056, 0.00583715)))) * 0.785398;
	float occlusion = 0;
	for (int ring = 1; ring <= 3; ring++)
	{
		for (int i = 0; i < 4; i++)
		{
			float angle = (i + ring * 0.33) * 0.785398 + jitter;	// 4 directions per ring, rings offset by 15 degrees
			float2 o = float2(cos(angle), sin(angle)) * scale * (ring / 3.0);
			float dp = CnvDepth(uv + o);
			float dm = CnvDepth(uv - o);
			float crease = d0 - 0.5 * (dp + dm);			// > 0: the centre lies deeper than both neighbours
			float gap = max(abs(dp - d0), abs(dm - d0));
			float weight = saturate(2 - gap / CNV_AO_RANGE);
			occlusion += saturate((crease - CNV_AO_CREASE_MIN) / CNV_AO_CREASE) * weight;
		}
	}
	return 1 - CNV_AO_STRENGTH * occlusion / 12;
}

float3 CnvSharpen(float3 color, float2 uv, float2 px)
{
	float3 n = tex2Dlod(SAMPLER(FrameBufferSampler), float4(uv + float2(px.x, 0), 0, 0)).xyz
	         + tex2Dlod(SAMPLER(FrameBufferSampler), float4(uv - float2(px.x, 0), 0, 0)).xyz
	         + tex2Dlod(SAMPLER(FrameBufferSampler), float4(uv + float2(0, px.y), 0, 0)).xyz
	         + tex2Dlod(SAMPLER(FrameBufferSampler), float4(uv - float2(0, px.y), 0, 0)).xyz;
	return max(0, color + (color - n * 0.25) * CNV_SHARPEN);
}

float3 CnvGrade(float3 color)
{
	color = saturate(color);
	float luma = dot(color, float3(0.299, 0.587, 0.114));
	color = lerp(luma.xxx, color, CNV_SATURATION);
	return lerp(color, color * color * (3 - 2 * color), CNV_CONTRAST);
}

#endif // CNV_ENHANCE_FXH
